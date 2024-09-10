import asyncio
import logging

import aio_pika
from aio_pika.patterns import RPC
import motor.motor_asyncio as aio_mongo
from decorator import decorator

from common.executors import AsyncioExecutor
from common.models import Teavent
from eventmanager.teavents_db import TeaventsDB
from eventmanager.protocol import RmqProtocol
from eventmanager.manager import TeaventManager


@decorator
def rethrow_exceptions_as(f, cls=RuntimeError, *args, **kwargs):
    try:
        return f(*args, **kwargs)
    except Exception as e:
        raise cls(str(e)) from e


async def main():
    logging.basicConfig(level=logging.INFO)

    executor = AsyncioExecutor()

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq")
    mongoc = aio_mongo.AsyncIOMotorClient("mongodb://admin:pass@mongodb")
    teavents_db = TeaventsDB(mongoc.eventmanager.teavents, executor=executor)

    async with connection:
        channel = await connection.channel()

        teavents_q = await channel.declare_queue("teavents", durable=True)
        outgoing_updates_q = await channel.declare_queue(
            "outgoing_updates", durable=True
        )
        await channel.set_qos(prefetch_size=0)

        protocol = RmqProtocol(outgoing_updates_q, channel, executor=executor)

        logging.info("Init manager")
        manager = TeaventManager(executor=executor, listeners=[protocol, teavents_db])
        async for teavent in teavents_db.fetch_teavents():
            manager.handle_teavent(teavent)

        logging.info("Register RPC")

        rpc = await RPC.create(channel)
        # to view tracebacks of RPC-calls
        # rpc.host_exceptions = True

        async def list_teavents() -> list[Teavent]:
            return manager.list_teavents()

        # HACK: real exception might be not pickle-serializable, rethrow it as RuntimeError
        @rethrow_exceptions_as(cls=RuntimeError)
        def user_action(type: str, user_id: str, teavent_id: str):
            return manager.handle_user_action(
                type=type, user_id=user_id, teavent_id=teavent_id
            )

        await rpc.register("list_teavents", list_teavents, auto_delete=True)
        await rpc.register("user_action", user_action, auto_delete=True)

        logging.info("Register consumers")

        @rethrow_exceptions_as(cls=RuntimeError)
        def on_teavent(message: aio_pika.abc.AbstractIncomingMessage):
            manager.handle_teavent(Teavent.from_message(message))

        await teavents_q.consume(on_teavent, no_ack=True)

        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
