import asyncio
import logging

import aio_pika
from statemachine import State, StateMachine

from common.pika_pydantic import ModelMessage
from common.models import Event, FlowUpdate


class InconsistencyError(RuntimeError):
    """Inconsistency data found"""


class EventFlow(StateMachine):
    # states
    created = State(initial=True)
    partially_confirmed = State()
    confirmed = State()
    started = State()
    finished = State(final=True)

    # transitions
    confirm = (
        created.to(confirmed, cond="everyone_confirmed")
        | partially_confirmed.to(confirmed, cond="everyone_confirmed")
        | created.to(partially_confirmed)
    )
    start = confirmed.to(started)
    got_reject = confirmed.to(partially_confirmed)
    finish = started.to(finished)

    def __init__(self, event: Event):
        self._event = event

        super().__init__()

    def everyone_confirmed(self) -> bool:
        return self._event.confirmed

    @property
    def event(self) -> Event:
        return self._event


class EventManager:
    def __init__(self):
        self._events_sm: dict[str, EventFlow] = {}

    def get_event(self, event_id: str) -> Event | None:
        try:
            return self._events_sm[event_id].event
        except KeyError:
            return None

    def manage(self, event: Event):
        if event.id not in self._events_sm:
            logging.info(f"Got new event {event}")
            self._events_sm[event.id] = EventFlow(event)
            return

        logging.info(f"Got known event {event}")
        sm = self._events_sm[event.id]

        current_state = sm.current_state.id
        if event.state != sm.current_state.id:
            raise InconsistencyError(
                f"Event {event.id} has state {current_state}, but {event.state} received"
            )

    def on_update(self, update: FlowUpdate) -> Event:
        return self._events_sm[update.event_id].send(update.type)


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()

        events = await channel.declare_queue("events", durable=True)
        em_updates = await channel.declare_queue("em_updates", durable=True)
        user_updates = await channel.declare_queue("user_updates", durable=True)
        await channel.set_qos(prefetch_size=0)

        # TODO on state change callback
        event_manager = EventManager()

        async def on_event_message(message: aio_pika.abc.AbstractIncomingMessage):
            event = Event.from_message(message)

            if managed_event := event_manager.get_event(event.id):
                # we are already managing this event, drop old message and update tag
                await managed_event.ack_delivery(channel)
                managed_event._delivery_tag = event._delivery_tag
            else:
                # TODO: move to state change callback
                update = FlowUpdate(chat_id=event.chat_id, type="created")
                await channel.default_exchange.publish(
                    ModelMessage(update),
                    routing_key=em_updates.name,
                )

            event_manager.manage(event)

        async def on_update_message(message: aio_pika.abc.AbstractIncomingMessage):
            update = FlowUpdate.from_message(message)

            event = event_manager.on_update(update)
            await channel.default_exchange.publish(
                ModelMessage(event),
                routing_key=events.name,
            )

        logging.info("Start consuming")
        await events.consume(on_event_message)
        await user_updates.consume(on_update_message)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
