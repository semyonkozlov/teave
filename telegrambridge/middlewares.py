from collections.abc import Awaitable

import pydantic
import aiogram
import aio_pika

from common.pika_pydantic import ModelMessage


class QueueMiddleware(aiogram.BaseMiddleware):
    def __init__(self, queue: aio_pika.abc.AbstractQueue):
        self._queue = queue

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data[self._queue.name] = self
        return await handler(event, data)

    async def publish(self, msg: pydantic.BaseModel):
        await self._queue.channel.default_exchange.publish(
            ModelMessage(msg),
            routing_key=self._queue.name,
        )


class RpcMiddleware(aiogram.BaseMiddleware):
    def __init__(self, rpc_method: Awaitable):
        self._method = rpc_method

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data[self._method.name] = self._method
        return await handler(event, data)
