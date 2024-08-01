import base64
from collections.abc import Awaitable
import logging
import re

import aiogram
from aiogram import F
from aiogram.filters import Command
from pydantic import ValidationError

from common.models import Event
from telegrambridge.middlewares import CalendarMiddleware, QueueMiddleware


log = logging.getLogger(__name__)
router = aiogram.Router()


@router.message(Command(commands=["events"]))
async def handle_list_events(message: aiogram.types.Message, list_events: Awaitable):
    await message.reply(str(await list_events()))


pattern = re.compile(r"https://calendar\.google\.com/calendar/u/0\?cid=(.*)")


@router.message(F.text.regexp(pattern))
async def handle_create_events_from_gcal_link(
    message: aiogram.types.Message,
    calendar: CalendarMiddleware,
    events: QueueMiddleware,
):
    calendar_id_b64 = pattern.match(message.text).group(1)
    calendar_id = base64.b64decode(calendar_id_b64).decode()

    # TODO avoid double managing the same calendar, but watch new events

    gcal_events = await calendar.list_events(calendar_id)
    for item in gcal_events["items"]:
        event = Event.from_gcal_event(item, communication_ids=[str(message.chat.id)])
        await events.publish(event)

    num = len(gcal_events["items"])
    await message.reply(text=f"Got {num} events")


@router.message()
async def process_any_message(message: aiogram.types.Message):
    await message.reply(text="TODO Default handler")
