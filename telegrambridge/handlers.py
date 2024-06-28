import logging

import aiogram
from pydantic import ValidationError

from common.models import Submit
from telegrambridge.middlewares import AsyncQueue


log = logging.getLogger(__name__)
router = aiogram.Router()


@router.message()
async def process_any_message(message: aiogram.types.Message, submits: AsyncQueue):
    try:
        submit = Submit.model_validate_json(message.text)
        submit.chat_id = str(message.chat.id)

        await submits.publish(submit.model_dump_json().encode())
        await message.reply(text="submit received")
    except ValidationError as e:
        log.error(e)
        await message.reply(text=str(e))
