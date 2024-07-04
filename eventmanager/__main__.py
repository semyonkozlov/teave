import asyncio
import logging

import aiormq
from statemachine import State, StateMachine

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

    connection = await aiormq.connect("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()

    events = await channel.queue_declare(queue="events", durable=True)
    em_updates = await channel.queue_declare(queue="em_updates", durable=True)
    user_updates = await channel.queue_declare(queue="user_updates", durable=True)
    await channel.basic_qos(prefetch_size=0)

    # TODO on state change callback
    event_manager = EventManager()

    async def on_event_message(message: aiormq.abc.DeliveredMessage):
        event = Event.model_validate_json(message.body)

        if managed_event := event_manager.get_event(event.id):
            await channel.basic_ack(managed_event.delivery_tag)
            managed_event.delivery_tag = message.delivery_tag
        else:
            # TODO: move to state change callback
            update = FlowUpdate(chat_id=event.chat_id, type="created")
            await channel.basic_publish(
                update.model_dump_json().encode(),
                routing_key=em_updates.queue,
                properties=aiormq.spec.Basic.Properties(delivery_mode=2),
            )

        event_manager.manage(event)

    async def on_update_message(message: aiormq.abc.DeliveredMessage):
        update = FlowUpdate.model_validate_json(message.body)

        event = event_manager.on_update(update)
        await channel.basic_publish(
            event.model_dump_json().encode(),
            routing_key=events.queue,
            properties=aiormq.spec.Basic.Properties(delivery_mode=2),
        )

    logging.info("Start consuming")
    await channel.basic_consume(events.queue, on_event_message)
    await channel.basic_consume(user_updates.queue, on_update_message)


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        pass
