from collections.abc import Coroutine
import logging
import re

import aiogram
from aiogram import F
from aiogram.types import ReactionTypeEmoji
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram_dialog import DialogManager, ShowMode, StartMode

from common.flow import TeaventFlow
from telegrambridge.dialogs import ManageNewTeavents, TeaventAdmin
from telegrambridge.filters import IsAdmin
from telegrambridge.keyboards import IAmLateAction, PlannedPollAction, RegPollAction
from telegrambridge.views import TgTeaventViewFactory, render_teavents


log = logging.getLogger(__name__)
router = aiogram.Router()

deep_link = re.compile(r"(.*)_(.*)")


@router.message(
    CommandStart(deep_link=True, magic=F.args.regexp(deep_link).as_("match"))
)
async def handle_deeplink(
    message: aiogram.types.Message,
    user_action: Coroutine,
    match: re.Match[str],
):
    action_type, teavent_id = match.groups()

    try:
        await user_action(
            type=action_type,
            user_id=str(message.from_user.id),
            teavent_id=teavent_id,
        )
        await message.react([ReactionTypeEmoji(emoji="👍")])
    except Exception as e:
        await message.react([ReactionTypeEmoji(emoji="👨‍💻")])
        await message.reply(text=str(e))


@router.message(
    Command(
        commands=[
            TeaventFlow.start_poll.name,
            TeaventFlow.stop_poll.name,
            TeaventFlow.start_.name,
            TeaventFlow.end.name,
            TeaventFlow.cancel.name,
            TeaventFlow.recreate.name,
        ]
    ),
    IsAdmin(),
)
async def handle_admin_actions(
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


@router.message(Command("view"), IsAdmin())
async def handle_view(
    message: aiogram.types.Message,
    command: CommandObject,
    get_teavent: Coroutine,
    view_factory: TgTeaventViewFactory,
):
    teavent = await get_teavent(id=command.args)

    view = view_factory.create_view(teavent.state)
    await view.show(teavent)


@router.message(Command("teavents"))
async def handle_command_teavents(
    message: aiogram.types.Message, list_teavents: Coroutine
):
    content = render_teavents(await list_teavents())
    await message.reply(**content.as_kwargs())


@router.message(Command("new"), IsAdmin())
async def handle_command_new(
    message: aiogram.types.Message,
    dialog_manager: DialogManager,
):
    await dialog_manager.start(
        ManageNewTeavents.ask_for_schedule,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.DELETE_AND_SEND,
    )

    try:
        await message.delete()
    except:
        log.exception("Can't delete message")


@router.message(Command(re.compile("settings_(.*)")), IsAdmin())
async def handle_command_settings_with_teavent_id(
    message: aiogram.types.Message,
    command: CommandObject,
    dialog_manager: DialogManager,
):
    teavent_id = command.regexp_match.group(1)

    await dialog_manager.start(
        TeaventAdmin.teavent_settings,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.DELETE_AND_SEND,
        data={"selected_teavent_id": teavent_id},
    )
    try:
        await message.delete()
    except:
        log.exception("Can't delete message")


@router.message(Command("settings"), IsAdmin())
async def handle_command_settings(
    message: aiogram.types.Message,
    dialog_manager: DialogManager,
):
    await dialog_manager.start(
        TeaventAdmin.select_teavent,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.DELETE_AND_SEND,
    )
    try:
        await message.delete()
    except:
        log.exception("Can't delete message")


@router.callback_query(RegPollAction.filter())
async def handle_reg_poll_action(
    callback: aiogram.types.CallbackQuery,
    callback_data: RegPollAction,
    user_action: Coroutine,
    view_factory: TgTeaventViewFactory,
):
    try:
        updated_teavent = await user_action(
            type=callback_data.action,
            user_id=f"@{callback.from_user.username}",
            teavent_id=callback_data.teavent_id,
        )
    except Exception as e:
        return await callback.answer(str(e), show_alert=True)

    view = view_factory.create_view(TeaventFlow.poll_open.value)

    await view.update(
        callback.message,
        teavent=updated_teavent,
    )

    return await callback.answer()


@router.callback_query(PlannedPollAction.filter())
async def handle_planned_poll_action(
    callback: aiogram.types.CallbackQuery,
    callback_data: PlannedPollAction,
    user_action: Coroutine,
    view_factory: TgTeaventViewFactory,
):
    try:
        updated_teavent = await user_action(
            type=callback_data.action,
            user_id=f"@{callback.from_user.username}",
            teavent_id=callback_data.teavent_id,
        )
    except Exception as e:
        return await callback.answer(str(e), show_alert=True)

    view = view_factory.create_view(TeaventFlow.planned.value)

    await view.update(
        callback.message,
        teavent=updated_teavent,
    )

    return await callback.answer()


@router.callback_query(IAmLateAction.filter())
async def handle_i_am_late_action(
    callback: aiogram.types.CallbackQuery,
    callback_data: IAmLateAction,
    user_action: Coroutine,
    view_factory: TgTeaventViewFactory,
):
    try:
        updated_teavent = await user_action(
            type=callback_data.action,
            user_id=f"@{callback.from_user.username}",
            teavent_id=callback_data.teavent_id,
        )
    except Exception as e:
        return await callback.answer(str(e), show_alert=True)

    view = view_factory.create_view(TeaventFlow.started.value)

    await view.update(
        callback.message,
        teavent=updated_teavent,
    )

    return await callback.answer()


@router.message(Command("tasks"), IsAdmin())
async def handle_tasks(message: aiogram.types.Message, tasks: Coroutine):
    await message.reply(str(await tasks()))
