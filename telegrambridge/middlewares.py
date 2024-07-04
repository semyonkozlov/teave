import pydantic
import aiogram
import aio_pika


class QueueMiddleware(aiogram.BaseMiddleware):
    def __init__(self, queue: aio_pika.abc.AbstractQueue):
        self._queue = queue

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data[self._queue.name] = self
        return await handler(event, data)

    async def publish(self, msg: pydantic.BaseModel):
        await self._queue.channel.default_exchange.publish(
            aio_pika.Message(
                msg.model_dump_json().encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=self._queue.name,
        )
