import asyncio
import logging

import aio_pika
from aio_pika.patterns import RPC
from attr import define
from statemachine import State, StateMachine

from common.pika_pydantic import ModelMessage
from common.models import Teavent, FlowUpdate


class InconsistencyError(RuntimeError):
    """Inconsistency data found"""


class TeaventFlow(StateMachine):
    # states
    created = State(initial=True)
    not_enough_participants = State()
    enough_participants = State()
    started = State()
    finished = State(final=True)

    # transitions
    # fmt: off
    confirm = created.to(enough_participants, cond="ready") | not_enough_participants.to(enough_participants, cond="ready") | created.to(not_enough_participants)
    start = enough_participants.to(started)
    reject = enough_participants.to(not_enough_participants, unless="ready")
    finish = started.to(finished)
    # fmt: on

    @property
    def teavent(self) -> Teavent:
        return self.model


@define(hash=True)
class QueueView:
    _teavents_queue: aio_pika.abc.AbstractQueue
    _outgoing_updates_queue: aio_pika.abc.AbstractQueue

    _channel: aio_pika.abc.AbstractChannel

    async def on_enter_state(self, state: State, model: Teavent):
        await self.publish_update(FlowUpdate.for_teavent(model, type=state.name))

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

    async def ack_teavent(self, teavent: Teavent, new_delivery_tag: str):
        "Drop old message from queue and update delivery tag"

        await teavent.ack_delivery(self._channel)
        teavent._delivery_tag = new_delivery_tag


@define
class TeaventManager:
    _view: QueueView
    _teavents_sm: dict[str, TeaventFlow] = {}

    def get_event(self, event_id: str) -> Teavent | None:
        try:
            return self._teavents_sm[event_id].teavent
        except KeyError:
            return None

    def list_events(self) -> list[Teavent]:
        return list(sm.teavent for sm in self._teavents_sm.values())

    async def _setup_timers(self, teavent: Teavent): ...

    async def process_teavent(self, teavent: Teavent):
        if teavent.id not in self._teavents_sm:
            logging.info(f"Got new event {teavent}")
            self._teavents_sm[teavent.id] = TeaventFlow(
                model=teavent, listeners=[self._view]
            )
            await self._setup_timers(teavent)
            return

        logging.info(f"Got known event {teavent}")
        sm = self._teavents_sm[teavent.id]

        self._check_consistency(teavent, sm.teavent)
        await self._view.ack_teavent(sm.teavent, new_delivery_tag=teavent._delivery_tag)

    def _check_consistency(self, new_teavent: Teavent, managed_teavent: Teavent):
        assert new_teavent.id == managed_teavent.id

        if new_teavent.state != managed_teavent.state:
            raise InconsistencyError(
                f"Event {managed_teavent.id} has state '{managed_teavent.state}', but '{new_teavent.state}' received"
            )

    async def process_update(self, update: FlowUpdate):
        await self._teavents_sm[update.teavent_id].send(update.type)


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()

        events = await channel.declare_queue("events", durable=True)
        incoming_updates = await channel.declare_queue("incoming_updates", durable=True)
        outgoing_updates = await channel.declare_queue("outgoing_updates", durable=True)
        await channel.set_qos(prefetch_size=0)

        qview = QueueView(events, outgoing_updates, channel)
        teavent_manager = TeaventManager(view=qview)

        logging.info("Register RPC")

        async def list_events() -> list[Teavent]:
            return teavent_manager.list_events()

        rpc = await RPC.create(channel)
        await rpc.register("list_events", list_events, auto_delete=True)

        logging.info("Register consumers")

        async def on_event_message(message: aio_pika.abc.AbstractIncomingMessage):
            await teavent_manager.process_teavent(Teavent.from_message(message))

        async def on_update_message(message: aio_pika.abc.AbstractIncomingMessage):
            await teavent_manager.process_update(FlowUpdate.from_message(message))

        await events.consume(on_event_message)
        await incoming_updates.consume(on_update_message)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
