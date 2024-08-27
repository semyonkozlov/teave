import asyncio
import logging

import aio_pika
from aio_pika.patterns import RPC

from common.errors import TeaveError
from common.executors import AsyncioExecutor
from common.models import Teavent
from eventmanager.protocol import RmqProtocol
from eventmanager.manager import TeaventManager


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()

        teavents = await channel.declare_queue("teavents", durable=True)
        outgoing_updates = await channel.declare_queue("outgoing_updates", durable=True)
        await channel.set_qos(prefetch_size=0)

        protocol = RmqProtocol(teavents, outgoing_updates, channel)
        executor = AsyncioExecutor()

        logging.info("Init manager")
        manager = TeaventManager(executor=executor, listeners=[protocol])
        for teavent in await protocol.fetch_teavents():
            try:
                manager.handle_teavent(teavent)
            except TeaveError:
                # TODO make it dry
                logging.exception(f"Drop teavent {teavent.id}")
                await protocol.drop(teavent._delivery_tag)

        logging.info("Register RPC")

        rpc = await RPC.create(channel)
        rpc.host_exceptions = True

        async def list_teavents() -> list[Teavent]:
            return manager.list_teavents()

        async def user_action(type: str, user_id: str, teavent_id: str):
            try:
                return manager.handle_user_action(
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
            try:
                managed_teavent = manager.handle_teavent(teavent)
            except TeaveError:
                logging.exception(f"Drop teavent {teavent.id}")
                await protocol.drop(teavent._delivery_tag)
                # TODO: drop also from manager
                return

            if managed_teavent is not None:
                prev_tag = managed_teavent.replace_tag(teavent._delivery_tag)
                await protocol.drop(prev_tag)

                # TODO: ugly: drop finalized teavent
                if managed_teavent.state == teavent.state == "finalized":
                    logging.info(f"Finalyzing teavent {teavent.id}")
                    manager.drop(managed_teavent.id)
                    await protocol.drop(managed_teavent._delivery_tag)

        await teavents.consume(on_teavent)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
