import base64
from collections.abc import Awaitable
import logging
import re

import aiogram
from aiogram import F
from aiogram.filters import Command
from aiogram.filters.command import CommandObject

from common.errors import EventDescriptionParsingError
from common.models import Teavent
from telegrambridge.filters import IsAdmin
from telegrambridge.middlewares import (
    CalendarMiddleware,
    QueueMiddleware,
)


log = logging.getLogger(__name__)
router = aiogram.Router()

gcal_link = re.compile(r"https://calendar\.google\.com/calendar/u/0\?cid=(.*)")


@router.message(F.text.regexp(gcal_link).as_("match"))
async def handle_create_teavents_from_gcal_link(
    message: aiogram.types.Message,
    calendar: CalendarMiddleware,
    teavents: QueueMiddleware,
    match: re.Match[str],
):
    calendar_id = base64.b64decode(match.group(1)).decode()

    # TODO avoid double managing the same calendar, but watch new events

    gcal_events = await calendar.list_events(calendar_id)
    teavents_to_publish = []
    for item in gcal_events["items"]:
        try:
            teavents_to_publish.append(
                Teavent.from_gcal_event(item, communication_ids=[str(message.chat.id)])
            )
        except EventDescriptionParsingError as e:
            event_link = item["htmlLink"]
            await message.reply(text=f"Event {event_link} has bad description: {e}")
            raise

    for teavent in teavents_to_publish:
        await teavents.publish(teavent)

    num = len(teavents_to_publish)
    links = "\n".join(e.link for e in teavents_to_publish)
    await message.reply(text=f"Got {num} teavents:\n {links}")


# TODO unused
def from_eid(eid: str) -> str:
    decoded = base64.b64decode(eid + "==").decode()
    event_id, calendar_id = decoded.split(" ")
    return event_id


@router.message(Command(commands=["confirm", "reject"]))
async def handle_user_actions(
    message: aiogram.types.Message,
    command: CommandObject,
    user_action: Awaitable,
):
    try:
        reply = await user_action(
            type=command.command,
            user_id=str(message.from_user.id),
            teavent_id=command.args,
        )
    except Exception as e:
        await message.reply(text=str(e))
        return

    await message.reply(text=str(reply))


@router.message(
    Command(commands=["poll_start", "poll_stop", "cancel", "start_", "finish"]),
    IsAdmin(),
)
async def handle_admin_actions(
    message: aiogram.types.Message,
    command: CommandObject,
    user_action: Awaitable,
):
    try:
        reply = await user_action(
            type=command.command,
            user_id=str(message.from_user.id),
            teavent_id=command.args,
        )
    except Exception as e:
        await message.reply(text=str(e))
        return

    await message.reply(text=str(reply))


@router.message(Command("teavents"))
async def handle_command_teavents(
    message: aiogram.types.Message, list_teavents: Awaitable
):
    text = "\n".join(
        f"{t.id} state={t.state} participants={t.participant_ids}"
        for t in await list_teavents()
    )
    await message.reply(text=(text or "no teavents"))


@router.message()
async def handle_any_message(message: aiogram.types.Message):
    await message.reply(text="TODO Default handler")
