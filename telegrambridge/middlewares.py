from aiogram import BaseMiddleware
from aiogram.types import Message
import pika


class RabbitMqChannel(BaseMiddleware):
    def __init__(self, rabbitmq_host: str):
        connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
        channel = connection.channel()

        channel.queue_declare(queue="submits", durable=True)

        self._connection = connection
        self._channel = channel

    async def __call__(self, handler, event: Message, data):
        data["channel"] = self._channel
        return await handler(event, data)

    def __del__(self):
        self._connection.close()
