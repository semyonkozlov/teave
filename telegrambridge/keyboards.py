from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class RegPollActionFactory(CallbackData, prefix="reg_poll"):
    action: str


def get_regpoll_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirm", callback_data=RegPollActionFactory(action="confirm"))
    builder.button(text="Reject", callback_data=RegPollActionFactory(action="reject"))
    builder.adjust(2)
    return builder.as_markup()
