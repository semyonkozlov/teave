import logging

from decorator import decorator
from aiogram.filters.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import (
    Select,
    Group,
    Button,
    Back,
    SwitchTo,
    Cancel,
    Multiselect,
)
from aiogram_dialog.widgets.input import TextInput

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


def admin_dialog() -> Dialog:
    return Dialog(
        select_teavent(),
        teavent_settings(),
        confirm_cancel(),
        add_participants(),
        kick_participants(),
        on_close=on_close,
    )
