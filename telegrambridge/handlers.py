import base64
from collections.abc import Coroutine
import logging
import re

import aiogram
from aiogram import F
from aiogram.types import ReactionTypeEmoji
from aiogram.filters import Command
from aiogram.filters.command import CommandObject

from common.errors import EventDescriptionParsingError
from common.models import Teavent
from telegrambridge.filters import IsAdmin
from telegrambridge.keyboards import RegPollAction
from telegrambridge.middlewares import CalendarMiddleware, RmqMiddleware
from telegrambridge.views import TgStateViewFactory, render_teavents


log = logging.getLogger(__name__)
router = aiogram.Router()

gcal_link = re.compile(r"https://calendar\.google\.com/calendar/u/0\?cid=(.*)")


@router.message(F.text.regexp(gcal_link).as_("match"))
async def handle_create_teavents_from_gcal_link(
    message: aiogram.types.Message,
    calendar: CalendarMiddleware,
    teavents: RmqMiddleware,
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
    user_action: Coroutine,
):
    try:
        await user_action(
            type=command.command,
            user_id=str(message.from_user.id),
            teavent_id=command.args,
        )
        await message.react([ReactionTypeEmoji(emoji="👍")])
    except Exception as e:
        await message.react([ReactionTypeEmoji(emoji="👨‍💻")])
        await message.reply(text=str(e))


@router.message(Command(commands=["confirm", "reject"]))
async def handle_user_actions(
    message: aiogram.types.Message,
    command: CommandObject,
    user_action: Coroutine,
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
    user_action: Coroutine,
):
    await _handle_user_actions(message, command, user_action)


@router.message(Command("teavents"))
async def handle_command_teavents(
    message: aiogram.types.Message, list_teavents: Coroutine
):
    content = render_teavents(await list_teavents())
    await message.reply(**content.as_kwargs())


@router.callback_query(RegPollAction.filter())
async def handle_reg_poll_action(
    callback: aiogram.types.CallbackQuery,
    callback_data: RegPollAction,
    user_action: Coroutine,
    view_factory: TgStateViewFactory,
):
    try:
        updated_teavent = await user_action(
            type=callback_data.action,
            user_id=str(callback.from_user.id),
            teavent_id=callback_data.teavent_id,
        )
    except Exception as e:
        return await callback.answer(str(e), show_alert=True)

    view = view_factory.create_view("poll_open")

    await view.update(
        callback.message,
        teavent=updated_teavent,
    )

    return await callback.answer()


@router.message()
async def handle_any_message(message: aiogram.types.Message):
    await message.reply(text="TODO Default handler")
