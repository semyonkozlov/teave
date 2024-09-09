from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class RegPollAction(CallbackData, prefix="reg_poll"):
    action: str
    teavent_id: str


def get_regpoll_keyboard(teavent_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Confirm",
        callback_data=RegPollAction(action="confirm", teavent_id=teavent_id),
    )
    builder.button(
        text="Reject",
        callback_data=RegPollAction(action="reject", teavent_id=teavent_id),
    )
    builder.adjust(2)
    return builder.as_markup()
