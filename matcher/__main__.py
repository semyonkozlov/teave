import asyncio
from collections import defaultdict
import logging

import aio_pika

from common.models import Teavent, Submit, UserType
from common.pika_pydantic import ModelMessage


class Matcher:
    def __init__(self):
        self._pending_events: dict[str, list[Teavent]] = defaultdict(list)
        self._unmatched_submits: dict[str, list[Submit]] = defaultdict(list)

    def match(self, submit: Submit) -> Teavent | None:
        match submit.user_type:
            case UserType.LEAD:
                event = Teavent(lead=submit)

                still_unmatched = list()

                for s in self._unmatched_submits[event.type]:
                    if not self._match(s, event):
                        still_unmatched.append(s)

                self._unmatched_submits[event.type] = still_unmatched

                if event.packed:
                    return event
                else:
                    self._pending_events[event.type].append(event)

            case UserType.FOLLOWER:
                pending_events = self._pending_events[submit.event_type]
                for e in pending_events:
                    if self._match(submit, e):
                        if e.packed:
                            pending_events.remove(e)  # TODO check
                            return e
                        break
                else:
                    self._unmatched_submits[submit.event_type].append(submit)
            case _:
                raise ValueError(f"Unknown user type {submit.user_type}")

        return None

    def _match(self, submit: Submit, event: Teavent):
        if submit.user_type != UserType.FOLLOWER:
            raise ValueError(f"Can match only submits of type {UserType.FOLLOWER}")

        logging.info(f"Matching submit {submit}...")

        if event.packed:
            logging.info("Event is already packed")
            return False

        if submit.event_type != event.type:
            logging.info(f"submit[{submit.event_type}] != event[{event.type}]")
            return False

        event.followers.append(submit)
        return True


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()

        submits = await channel.declare_queue("submits", durable=True)
        events = await channel.declare_queue("events", durable=True)
        await channel.set_qos(prefetch_size=0)

        async def ack_submits(event: Teavent):
            for submit in event.followers:
                await submit.ack_delivery(channel)
            await event.lead.ack_delivery(channel)

        async def publish_event(event: Teavent):
            assert event.packed
            logging.info(f"Event {event} is packed, publishing...")

            await ack_submits(event)
            await channel.default_exchange.publish(
                ModelMessage(event), routing_key=events.name
            )

        matcher = Matcher()

        async def on_submit(message: aio_pika.abc.AbstractIncomingMessage):
            submit = Submit.from_message(message)
            if event := matcher.match(submit):
                await publish_event(event)

        logging.info("Start consuming")
        await submits.consume(on_submit)
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
