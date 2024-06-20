import logging

import pika
from aiogram import Router
from aiogram.types import Message
from pydantic import ValidationError

from common.models import Submit


log = logging.getLogger(__name__)
router = Router()


@router.message()
async def process_any_message(message: Message, channel):
    try:
        Submit.model_validate_json(message.text)

        channel.basic_publish(
            exchange="",
            routing_key="submits",
            body=message.text,
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
            ),
        )
        await message.reply(text=message.text)
    except ValidationError as e:
        log.error(e)
        await message.reply(text=str(e))
