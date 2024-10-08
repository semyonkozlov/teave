import base64
import logging
import operator
import re

from aiogram import F
from decorator import decorator
from aiogram.filters.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import (
    Select,
    Group,
    Button,
    Next,
    Back,
    SwitchTo,
    Cancel,
    Multiselect,
)
from aiogram_dialog.widgets.input import TextInput

from common.errors import EventDescriptionParsingError
from common.models import Teavent

log = logging.getLogger(__name__)


@decorator
async def finish_dialog(func, *args, **kwargs):
    manager: DialogManager = args[2]

    try:
        await func(*args, **kwargs)
        await manager.done()
    except Exception as e:
        await manager.done(e)


class TeaventAdmin(StatesGroup):
    select_teavent = State()
    teavent_settings = State()
    confirm_cancel = State()
    confirm_reset = State()
    add_participants = State()
    kick_participants = State()


async def get_teavents(**kwargs) -> dict:
    teavents = await kwargs["list_teavents"]()
    return {
        "teavents": teavents,
        "count": len(teavents),
    }


async def on_teavent_selected(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    item_id: str,
):
    manager.dialog_data["selected_teavent_id"] = item_id
    await manager.switch_to(TeaventAdmin.teavent_settings)


def select_teavent() -> Window:
    return Window(
        Const("Выберите событие"),
        Select(
            Format("{item.summary} в {item.start}"),
            id="select_teavents",
            item_id_getter=lambda t: t.id,
            items="teavents",
            on_click=on_teavent_selected,
        ),
        Cancel(Const("Закрыть")),  # TODO check show mode
        getter=get_teavents,
        state=TeaventAdmin.select_teavent,
    )


def teavent_settings() -> Window:
    return Window(
        Format("Настройки события {dialog_data[selected_teavent_id]}"),
        Group(
            SwitchTo(
                Const("Добавить участников"),
                id="settings.add_participants",
                state=TeaventAdmin.add_participants,
            ),
            SwitchTo(
                Const("Кикнуть участников"),
                id="settings.kick_participants",
                state=TeaventAdmin.kick_participants,
            ),
            SwitchTo(
                Const("Отменить событие"),
                id="settings.cancel",
                state=TeaventAdmin.confirm_cancel,
            ),
            Back(Const("<<")),
            width=2,
        ),
        state=TeaventAdmin.teavent_settings,
    )


@finish_dialog
async def do_cancel(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
):
    user_action = manager.middleware_data["user_action"]

    await user_action(
        type="cancel",
        user_id=f"@{callback.from_user.username}",
        teavent_id=manager.dialog_data["selected_teavent_id"],
    )


def confirm_cancel() -> Window:
    return Window(
        Format("Отменить {dialog_data[selected_teavent_id]}?"),
        Button(
            Const("Да"),
            id="cancel.yes",
            on_click=do_cancel,
        ),
        SwitchTo(
            Const("Нет"),
            id="cancel.no",
            state=TeaventAdmin.teavent_settings,
        ),
        state=TeaventAdmin.confirm_cancel,
    )


async def do_add(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    data: str,
):
    user_action = manager.middleware_data["user_action"]
    teavent_id = manager.dialog_data["selected_teavent_id"]

    # TODO handle errors
    for user_id in data.split(","):
        await user_action(
            type="confirm",
            user_id=user_id.strip(),
            teavent_id=teavent_id,
        )


def add_participants() -> Window:
    return Window(
        Const("Введите имена участников через ,"),
        SwitchTo(
            Const("Отмена"),
            id="add_participants.cancel",
            state=TeaventAdmin.teavent_settings,
        ),
        TextInput(
            id="add_participants.input",
            on_success=do_add,
        ),
        state=TeaventAdmin.add_participants,
        # markup_factory=ReplyKeyboardFactory(
        #     input_field_placeholder=Const("@username, ...")
        # ),
    )


async def get_partcipants(**kwargs):
    teavent_id = kwargs["dialog_manager"].dialog_data["selected_teavent_id"]
    teavent: Teavent = await kwargs["get_teavent"](id=teavent_id)

    participants = teavent.participant_ids

    return {
        "participants": participants,
        "count": len(participants),
    }


async def _do_kick(user_action, participant_ids: list[str], teavent_id: str):
    for participant_id in participant_ids:
        await user_action(
            type="reject",
            user_id=participant_id,
            teavent_id=teavent_id,
        )


async def do_kick_checked(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
):
    mselect: Multiselect = manager.find("kick_participants.mselect")

    await _do_kick(
        user_action=manager.middleware_data["user_action"],
        participant_ids=mselect.get_checked(),
        teavent_id=manager.dialog_data["selected_teavent_id"],
    )


async def do_kick_input(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    data: str,
):
    await _do_kick(
        user_action=manager.middleware_data["user_action"],
        participant_ids=[s.strip() for s in data.split(",")],
        teavent_id=manager.dialog_data["selected_teavent_id"],
    )


def kick_participants() -> Window:
    return Window(
        Const("Введите имя участников через , или выберите из списка"),
        Multiselect(
            Format("✓ {item}"),
            Format("{item}"),
            id="kick_participants.mselect",
            item_id_getter=lambda x: x,
            items="participants",
        ),
        Button(
            Const("Kick"),
            id="kick_participants.confirm",
            on_click=do_kick_checked,
        ),
        SwitchTo(
            Const("Отмена"),
            id="kick_participants.cancel",
            state=TeaventAdmin.teavent_settings,
        ),
        TextInput(
            id="kick_participants.input",
            on_success=do_kick_input,
        ),
        getter=get_partcipants,
        state=TeaventAdmin.kick_participants,
    )


async def on_close(result, manager: DialogManager):
    event: CallbackQuery | Message = manager.event

    if isinstance(event, CallbackQuery):
        if result is not None:
            await event.answer(str(result), show_alert=True)

        await manager.event.message.delete()
    elif isinstance(event, Message):
        if result is not None:
            await event.reply(str(result))


async def on_start(start_data, manager: DialogManager):
    if start_data is not None:
        manager.dialog_data.update(start_data)


def admin_dialog() -> Dialog:
    return Dialog(
        select_teavent(),
        teavent_settings(),
        confirm_cancel(),
        add_participants(),
        kick_participants(),
        on_start=on_start,
        on_close=on_close,
    )


class ManageNewTeavents(StatesGroup):
    ask_for_schedule = State()
    confirm_fetched_teavents = State()
    ask_for_chats = State()


async def fetch_teavents(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    match: re.Match[str],
):
    calendar = manager.middleware_data["calendar"]
    calendar_id = base64.b64decode(match.group(1)).decode()

    # TODO avoid double managing the same calendar, but watch new events

    gcal_events = await calendar.list_events(calendar_id)

    items = manager.dialog_data["gcal_items"] = gcal_events["items"]
    manager.dialog_data["gcal_events_count"] = len(items)

    await manager.next()


gcal_link = re.compile(r"https://calendar\.google\.com/calendar/u/0\?cid=(.*)")


class BadCalendarLink(ValueError):
    """Input is not a correct calendar link"""


def match_link(input: str) -> re.Match[str]:
    match = gcal_link.match(input)
    if match is None:
        raise BadCalendarLink(f"'{input}' is not valid gcal link")
    return match


async def show_error(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    error: BadCalendarLink,
):
    await message.reply(str(error))


def ask_for_schedule() -> Window:
    return Window(
        Const("Пришлите мне ссылку c расписанием"),
        TextInput(
            id="provide_teavents.input",
            type_factory=match_link,
            on_success=fetch_teavents,
            on_error=show_error,
        ),
        Cancel(
            Const("Отмена"),
        ),
        state=ManageNewTeavents.ask_for_schedule,
    )


async def parse_teavents(
    callback: CallbackQuery, button: Button, manager: DialogManager
):
    teavents = manager.dialog_data["teavents"] = []

    for item in manager.dialog_data["gcal_items"]:
        if item["status"] == "cancelled":
            # TODO should not skip cancelled event as it could be cancelled recurring instance
            log.warning(f"Skip cancelled event: {item}")
            continue

        try:
            teavents.append(Teavent.from_gcal_event(item))
        except EventDescriptionParsingError as e:
            await callback.message.answer(str(e))
            raise


def confirm_fetched_teavents() -> Window:
    return Window(
        Format("Вижу {dialog_data[gcal_events_count]} событий. Добавить их в бота?"),
        Next(
            Const("Добавить"),
            on_click=parse_teavents,
        ),
        Cancel(
            Const("Отмена"),
        ),
        state=ManageNewTeavents.confirm_fetched_teavents,
    )


async def start_managing_teavents(
    callback: CallbackQuery, button: Button, manager: DialogManager
):
    mselect: Multiselect = manager.find("ask_for_chats.mselect")
    # TODO: get chats from mselect

    communication_ids = [str(callback.message.chat.id)]

    manage_teavent = manager.middleware_data["manage_teavent"]

    for teavent in manager.dialog_data["teavents"]:
        try:
            teavent.communication_ids = communication_ids
            await manage_teavent(teavent=teavent)
        except Exception as e:
            await manager.done(e)

    await manager.done()


async def get_bot_chats(**kwargs):
    # TODO get chats from db
    bot_chats = []

    return {
        "bot_chats": bot_chats,
        "count": len(bot_chats),
    }


def ask_for_chats() -> Window:
    return Window(
        Format("В каких чатах запускать голосование?"),
        Multiselect(
            Format("✓ {item[1]}"),
            Format("{item[1]}"),
            id="ask_for_chats.mselect",
            item_id_getter=lambda x: operator.itemgetter(0),
            items="bot_chats",
        ),
        Button(
            Const("Выбрать"),
            id="ask_for_chats.confirm",
            on_click=start_managing_teavents,
        ),
        Cancel(
            Const("Отмена"),
        ),
        getter=get_bot_chats,
        state=ManageNewTeavents.ask_for_chats,
    )


def new_teavents_dialog() -> Dialog:
    return Dialog(
        ask_for_schedule(),
        confirm_fetched_teavents(),
        ask_for_chats(),
        on_close=on_close,
    )
