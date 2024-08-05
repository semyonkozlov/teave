import base64
from collections.abc import Awaitable
import logging
import re

import aiogram
from aiogram import F
from aiogram.filters import Command
from aiogram.filters.command import CommandObject

from common.errors import EventDescriptionParsingError
from common.models import FlowUpdate, Teavent
from telegrambridge.middlewares import CalendarMiddleware, QueueMiddleware


log = logging.getLogger(__name__)
router = aiogram.Router()


@router.message(Command(commands=["events"]))
async def handle_list_events(message: aiogram.types.Message, list_events: Awaitable):
    await message.reply(str(await list_events()))


pattern = re.compile(r"https://calendar\.google\.com/calendar/u/0\?cid=(.*)")


@router.message(F.text.regexp(pattern).as_("match"))
async def handle_create_events_from_gcal_link(
    message: aiogram.types.Message,
    calendar: CalendarMiddleware,
    events: QueueMiddleware,
    match: re.Match[str],
):
    calendar_id = base64.b64decode(match.group(1)).decode()

    # TODO avoid double managing the same calendar, but watch new events

    gcal_events = await calendar.list_events(calendar_id)
    events_to_publish = []
    for item in gcal_events["items"]:
        try:
            events_to_publish.append(
                Teavent.from_gcal_event(item, communication_ids=[str(message.chat.id)])
            )
        except EventDescriptionParsingError as e:
            event_link = item["htmlLink"]
            await message.reply(text=f"Event {event_link} has bad description: {e}")
            raise

    for event in events_to_publish:
        await events.publish(event)

    num = len(events_to_publish)
    links = "\n".join(e.link for e in events_to_publish)
    await message.reply(text=f"Got {num} events:\n {links}")


def from_eid(eid: str) -> str:
    decoded = base64.b64decode(eid + "==").decode()
    event_data, calendar_data = decoded.split(" ")
    event_id, time_data = event_data.split("_")
    return event_id


@router.message(Command(commands=["confirm", "reject", "submit", "start_"]))
async def process_command(
    message: aiogram.types.Message,
    command: CommandObject,
    incoming_updates: QueueMiddleware,
):
    await incoming_updates.publish(
        FlowUpdate(
            teavent_id=from_eid(command.args),
            communication_ids=[str(message.chat.id)],
            type=command.command,
        )
    )


@router.message()
async def process_any_message(message: aiogram.types.Message):
    await message.reply(text="TODO Default handler")
