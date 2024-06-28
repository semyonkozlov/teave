import aiogram
import aiormq


class AsyncQueue(aiogram.BaseMiddleware):
    def __init__(self, channel: aiormq.abc.AbstractChannel, queue_name: str):
        self._channel = channel
        self._queue_name = queue_name

    async def __call__(self, handler, event: aiogram.types.Message, data):
        data[self._queue_name] = self
        return await handler(event, data)

    async def publish(self, msg: bytearray):
        await self._channel.basic_publish(
            msg,
            routing_key=self._queue_name,
            properties=aiormq.spec.Basic.Properties(delivery_mode=2),  # persistent
        )
