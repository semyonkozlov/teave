import asyncio
import logging

import aio_pika
from aio_pika.patterns import RPC
from attr import define
from statemachine import State, StateMachine

from common.pika_pydantic import ModelMessage
from common.models import Event, FlowUpdate


class InconsistencyError(RuntimeError):
    """Inconsistency data found"""


class EventFlow(StateMachine):
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
    def event(self) -> Event:
        return self.model


@define
class QueueView:

    _events_queue: aio_pika.abc.AbstractQueue
    _outgoing_updates_queue: aio_pika.abc.AbstractQueue

    _channel: aio_pika.abc.AbstractChannel

    async def publish_update(self, outgoing_update: FlowUpdate):
        await self._channel.default_exchange.publish(
            ModelMessage(outgoing_update),
            routing_key=self._outgoing_updates_queue.name,
        )

    async def publish_event(self, event: Event):
        await self._channel.default_exchange.publish(
            ModelMessage(event),
            routing_key=self._events_queue.name,
        )

    async def ack_event(self, event: Event, new_delivery_tag: str):
        "Drop old message from queue and update delivery tag"

        await event.ack_delivery(self._channel)
        event._delivery_tag = new_delivery_tag


@define
class EventManager:

    _view: QueueView  # TODO subscribe view to events_sm
    _events_sm: dict[str, EventFlow] = {}

    def get_event(self, event_id: str) -> Event | None:
        try:
            return self._events_sm[event_id].event
        except KeyError:
            return None

    def list_events(self) -> list[Event]:
        return list(sm.event for sm in self._events_sm.values())

    async def _setup_timers(self, event: Event): ...

    async def process_event(self, event: Event):
        if event.id not in self._events_sm:
            logging.info(f"Got new event {event}")
            self._events_sm[event.id] = EventFlow(model=event)
            await self._setup_timers(event)
            return

        logging.info(f"Got known event {event}")
        sm = self._events_sm[event.id]

        self._check_consistency(event, sm.event)
        await self._view.ack_event(sm.event, new_delivery_tag=event._delivery_tag)

    def _check_consistency(self, new_event: Event, managed_event: Event):
        assert new_event.id == managed_event.id

        if new_event.state != managed_event.state:
            raise InconsistencyError(
                f"Event {managed_event.id} has state '{managed_event.state}', but '{new_event.state}' received"
            )

    async def process_update(self, update: FlowUpdate):
        updated_event = self._events_sm[update.event_id].send(update.type)
        await self._view.publish_event(updated_event)


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
        event_manager = EventManager(view=qview)

        logging.info("Register RPC")

        async def list_events() -> list[Event]:
            return event_manager.list_events()

        rpc = await RPC.create(channel)
        await rpc.register("list_events", list_events, auto_delete=True)

        logging.info("Register consumers")

        async def on_event_message(message: aio_pika.abc.AbstractIncomingMessage):
            await event_manager.process_event(Event.from_message(message))

        async def on_update_message(message: aio_pika.abc.AbstractIncomingMessage):
            await event_manager.process_update(FlowUpdate.from_message(message))

        await events.consume(on_event_message)
        await incoming_updates.consume(on_update_message)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
