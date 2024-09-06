import base64
from collections.abc import Awaitable
import logging
import re

import aiogram
from aiogram import F
from aiogram.types import ReactionTypeEmoji
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.utils.formatting import (
    as_list,
    as_section,
    as_key_value,
    TextLink,
    Bold,
    Text,
    Underline,
)

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
        if item["status"] == "cancelled":
            # TODO should not skip cancelled event as it could be cancelled recurring instance
            log.warning(f"Skip cancelled event: {item}")
            continue

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


async def _handle_user_actions(
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
        await message.react([ReactionTypeEmoji(emoji="👨‍💻")])
        await message.reply(text=str(e))
        return

    if reply is None:
        await message.react([ReactionTypeEmoji(emoji="👍")])
    else:
        await message.reply(text=str(reply))


@router.message(Command(commands=["confirm", "reject"]))
async def handle_user_actions(
    message: aiogram.types.Message,
    command: CommandObject,
    user_action: Awaitable,
):
    await _handle_user_actions(message, command, user_action)


# TODO: use state machine events to enum commands, move TeaventFlow to common
@router.message(
    Command(commands=["start_poll", "stop_poll", "cancel", "start_", "finish"]),
    IsAdmin(),
)
async def handle_admin_actions(
    message: aiogram.types.Message,
    command: CommandObject,
    user_action: Awaitable,
):
    await _handle_user_actions(message, command, user_action)


def _format_teavent(t: Teavent) -> Text:
    # fmt: off
    participants = as_list(*t.participant_ids) if t.participant_ids else ""

    return as_section(
        TextLink(t.summary, url=t.link),
        as_list(
            as_key_value("Статус", t.state),
            as_key_value("Начало", t.start),
            as_key_value("Продолжительность", t.duration),
            as_key_value("Участники", participants),
        )
    )
    # fmt: on


def _format_teavents(teavents: list[Teavent]) -> Text:
    # fmt: off
    return as_section(
        Bold(Underline("БЛИЖАЙШИЕ СОБЫТИЯ")),
        "\n",
        as_list(
            *(_format_teavent(t) for t in teavents),
            sep="\n\n",
        )
    )
    # fmt: on


@router.message(Command("teavents"))
async def handle_command_teavents(
    message: aiogram.types.Message, list_teavents: Awaitable
):
    content = _format_teavents(await list_teavents())
    await message.reply(**content.as_kwargs())


@router.message()
async def handle_any_message(message: aiogram.types.Message):
    await message.reply(text="TODO Default handler")
