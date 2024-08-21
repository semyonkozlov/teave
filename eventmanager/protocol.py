import asyncio

import aio_pika
from attr import define
from statemachine import State

from common.models import FlowUpdate, Teavent
from common.pika_pydantic import ModelMessage


@define(eq=False)  # eq=False for hashing by id
class RmqProtocol:
    _teavents_queue: aio_pika.abc.AbstractQueue
    _outgoing_updates_queue: aio_pika.abc.AbstractQueue

    _channel: aio_pika.abc.AbstractChannel

    _tasks: set[asyncio.Task] = set()

    async def publish_update(self, outgoing_update: FlowUpdate):
        await self._channel.default_exchange.publish(
            ModelMessage(outgoing_update),
            routing_key=self._outgoing_updates_queue.name,
        )

    async def publish_teavent(self, teavent: Teavent):
        await self._channel.default_exchange.publish(
            ModelMessage(teavent),
            routing_key=self._teavents_queue.name,
        )

    async def ack_teavent(self, teavent: Teavent, new_delivery_tag: str | None = None):
        "Drop old message from queue and update delivery tag"

        await teavent.ack_delivery(self._channel)
        teavent._delivery_tag = new_delivery_tag

    async def fetch_teavents(self) -> list[Teavent]:
        uniq_teavents = {}

        while message := await self._teavents_queue.get(fail=False):
            teavent = Teavent.from_message(message)
            if teavent.id in uniq_teavents:
                await self.ack_teavent(uniq_teavents[teavent.id])
            uniq_teavents[teavent.id] = teavent

        return list(uniq_teavents.values())

    # SM actions

    def on_enter_state(self, state: State, model: Teavent):
        async def _task():
            await self.publish_teavent(model)
            await self.publish_update(FlowUpdate.for_teavent(model, type=state.name))

        task = asyncio.create_task(_task())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
