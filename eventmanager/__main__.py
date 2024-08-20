import asyncio
import logging

import aio_pika
from aio_pika.patterns import RPC

from common.models import Teavent
from eventmanager.protocol import Protocol
from eventmanager.manager import TeaventManager


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()

        teavents = await channel.declare_queue("teavents", durable=True)
        outgoing_updates = await channel.declare_queue("outgoing_updates", durable=True)
        await channel.set_qos(prefetch_size=0)

        protocol = Protocol(teavents, outgoing_updates, channel)
        teavent_manager = TeaventManager(listeners=[protocol])

        logging.info("Register RPC")

        rpc = await RPC.create(channel)
        rpc.host_exceptions = True

        async def list_teavents() -> list[Teavent]:
            return teavent_manager.list_teavents()

        async def user_action(type: str, user_id: str, teavent_id: str):
            try:
                return teavent_manager.handle_user_action(
                    type=type, user_id=user_id, teavent_id=teavent_id
                )
            except Exception as e:
                # HACK: real exception might be not pickle-serializable, rethrow it as RuntimeError
                raise RuntimeError(str(e)) from e

        await rpc.register("list_teavents", list_teavents, auto_delete=True)
        await rpc.register("user_action", user_action, auto_delete=True)

        logging.info("Register consumers")

        async def on_teavent(message: aio_pika.abc.AbstractIncomingMessage):
            teavent = Teavent.from_message(message)
            if managed_teavent := teavent_manager.handle_teavent(teavent):
                await protocol.ack_teavent(
                    managed_teavent, new_delivery_tag=teavent._delivery_tag
                )

        await teavents.consume(on_teavent)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
