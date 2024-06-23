from collections import defaultdict
from collections.abc import Callable
import logging

import pika

from common.models import Event, Submit, UserType


class Matcher:
    def __init__(self, on_packed_event: Callable[[Event], None]):
        self._pending_events: dict[str, list[Event]] = defaultdict(list)
        self._unmatched_submits: dict[str, list[Submit]] = defaultdict(list)

        self._on_packed_event = on_packed_event

    def on_submit(self, submit: Submit):
        logging.info(f"New submit {submit}")

        match submit.user_type:
            case UserType.LEAD:
                event = Event(lead=submit)

                still_unmatched = list()

                for s in self._unmatched_submits[event.type]:
                    if not self._match(s, event):
                        still_unmatched.append(s)

                self._unmatched_submits[event.type] = still_unmatched

                if event.packed:
                    self._on_packed_event(event)
                else:
                    self._pending_events[event.type].append(event)

            case UserType.FOLLOWER:
                pending_events = self._pending_events[submit.event_type]
                for e in pending_events:
                    if self._match(submit, e):
                        if e.packed:
                            pending_events.remove(e)
                            self._on_packed_event(e)
                        break
                else:
                    self._unmatched_submits[submit.event_type].append(submit)
            case _:
                raise ValueError(f"Unknown user type {submit.user_type}")

    def _match(self, submit: Submit, event: Event):
        if submit.user_type != UserType.FOLLOWER:
            raise ValueError(f"Can match only submits of type {UserType.FOLLOWER}")

        logging.info(f"Matching submit {submit}")

        if event.packed:
            logging.info("Event is already packed")
            return False

        if submit.event_type != event.type:
            logging.info(f"submit[{submit.event_type}] != event[{event.type}]")
            return False

        event.followers.append(submit)
        return True


def main():
    logging.basicConfig(level=logging.INFO)

    connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq"))
    channel = connection.channel()

    channel.queue_declare(queue="submits", durable=True)
    channel.queue_declare(queue="events", durable=True)

    def ack_submits(event: Event):
        for submit in event.followers:
            channel.basic_ack(delivery_tag=submit.id)
        channel.basic_ack(delivery_tag=event.lead.id)

    def publish_event(event: Event):
        assert event.packed
        logging.info(f"Event {event} is packed, publishing")

        ack_submits(event)
        channel.basic_publish(
            exchange="",
            routing_key="events",
            body=event.model_dump_json(),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
            ),
        )

    matcher = Matcher(on_packed_event=publish_event)

    def callback(ch, method, properties, body):
        submit = Submit.model_validate_json(body)
        submit.id = method.delivery_tag
        matcher.on_submit(submit)

    channel.basic_qos(prefetch_size=0)
    channel.basic_consume(queue="submits", on_message_callback=callback)

    logging.info("Start consuming")
    channel.start_consuming()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
