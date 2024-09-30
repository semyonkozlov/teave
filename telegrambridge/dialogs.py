from aiogram.filters.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, LaunchMode, Window
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Select, Group, Button, Back, SwitchTo, Cancel
from aiogram_dialog.widgets.input import TextInput


class TeaventAdmin(StatesGroup):
    select_teavent = State()
    teavent_settings = State()
    confirm_cancel = State()
    confirm_reset = State()
    add_users = State()
    kick_users = State()


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
                id="settings.add_users",
                state=TeaventAdmin.add_users,
            ),
            SwitchTo(
                Const("Кикнуть участников"),
                id="settings.kick_users",
                state=TeaventAdmin.kick_users,
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
    await manager.done()


def confirm_cancel() -> Window:
    return Window(
        Format("Отменить {dialog_data[selected_teavent_id]}?"),
        Button(
            Const("Да"),
            id="cancel.yes",
            on_click=do_cancel,
        ),
        SwitchTo(Const("Нет"), id="cancel.no", state=TeaventAdmin.teavent_settings),
        state=TeaventAdmin.confirm_cancel,
    )


async def do_add_users(
    message: Message,
    button: Button,
    manager: DialogManager,
    data: str,
):
    user_action = manager.middleware_data["user_action"]
    for user_id in data.split(","):
        await user_action(
            type="confirm",
            user_id=user_id,
            teavent_id=manager.dialog_data["selected_teavent_id"],
        )
    await manager.done()


def add_users() -> Window:
    return Window(
        Const("Введите имена участников через ,"),
        SwitchTo(
            Const("<<"), id="add_users.cancel", state=TeaventAdmin.teavent_settings
        ),
        TextInput(
            id="add_users.input",
            on_success=do_add_users,
        ),
        state=TeaventAdmin.add_users,
    )


def kick_users() -> Window: ...


def admin_dialog() -> Dialog:
    return Dialog(
        select_teavent(),
        teavent_settings(),
        confirm_cancel(),
        add_users(),
        # kick_users(),
    )
