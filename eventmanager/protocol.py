import asyncio
from collections.abc import Coroutine
import logging

import aio_pika
from attr import define
from statemachine import State

from common.models import FlowUpdate, Teavent
from common.pika_pydantic import ModelMessage

log = logging.getLogger("protocol")


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

    async def drop(self, tag: int):
        log.info(f"Drop delivery_tag={tag}")

        underlay = await self._channel.get_underlay_channel()
        return await underlay.basic_ack(tag)

    async def fetch_teavents(self) -> list[Teavent]:
        uniq_teavents = {}

        while message := await self._teavents_queue.get(fail=False):
            teavent = Teavent.from_message(message)
            if prev_tag_teavent := uniq_teavents.get(teavent.id):
                await self.drop(prev_tag_teavent._delivery_tag)
            uniq_teavents[teavent.id] = teavent

        return list(uniq_teavents.values())

    async def _publish(self, teavent: Teavent, update_type: str):
        await self.publish_teavent(teavent)
        await self.publish_update(FlowUpdate.for_teavent(teavent, type=update_type))

    def _create_task(self, coro: Coroutine):
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # SM actions

    def on_enter_state(self, state: State, model: Teavent):
        log.info(f"on enter state {state.id}")

        self._create_task(
            self._publish(teavent=model.model_copy(), update_type=state.name)
        )

        if state.final:
            self._create_task(self.drop(tag=model._delivery_tag))
