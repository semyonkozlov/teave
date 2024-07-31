import base64
from collections.abc import Awaitable
import logging
import re

import aiogram
from aiogram import F
from aiogram.filters import Command
from pydantic import ValidationError

from common.models import Submit
from telegrambridge.middlewares import CalendarMiddleware, QueueMiddleware


log = logging.getLogger(__name__)
router = aiogram.Router()


@router.message(Command(commands=["events"]))
async def handle_list_events(message: aiogram.types.Message, list_events: Awaitable):
    await message.reply(str(await list_events()))


pattern = re.compile(r"https://calendar\.google\.com/calendar/u/0\?cid=(.*)")


@router.message(F.text.regexp(pattern))
async def handle_create_event_using_calendar_link(
    message: aiogram.types.Message, calendar: CalendarMiddleware
):
    calendar_id_b64 = pattern.match(message.text).group(1)
    calendar_id = base64.b64decode(calendar_id_b64).decode()
    events = await calendar.list_events(calendar_id)
    items = events["items"]
    await message.reply(text=f"Got {len(items)} events")


@router.message()
async def process_any_message(message: aiogram.types.Message, submits: QueueMiddleware):
    try:
        submit = Submit.model_validate_json(message.text)
        submit.chat_id = str(message.chat.id)

        await submits.publish(submit)
        await message.reply(text="submit received")
    except ValidationError as e:
        log.error(e)
        await message.reply(text=str(e))
