from aiogram import Router
from aiogram.types import Message
import pika


router = Router()


@router.message()
async def process_any_message(message: Message, channel):
    # TODO: use async channel
    channel.basic_publish(
        exchange="",
        routing_key="submits",
        body=message.text,
        properties=pika.BasicProperties(
            delivery_mode=pika.DeliveryMode.Persistent,
        ),
    )
    await message.reply(text=message.text)
