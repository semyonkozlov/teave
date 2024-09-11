from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class RegPollAction(CallbackData, prefix="reg_poll"):
    action: str
    teavent_id: str


def make_regpoll_keyboard(teavent_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Участвую",
        callback_data=RegPollAction(action="confirm", teavent_id=teavent_id),
    )
    builder.button(
        text="Не участвую",
        callback_data=RegPollAction(action="reject", teavent_id=teavent_id),
    )
    builder.adjust(2)
    return builder.as_markup()


class PlannedPollAction(CallbackData, prefix="planned_poll"):
    action: str
    teavent_id: str


def make_plannedpoll_keyboard(teavent_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Участвую",
        callback_data=PlannedPollAction(action="confirm", teavent_id=teavent_id),
    )
    builder.button(
        text="Отказаться от участия",
        callback_data=PlannedPollAction(action="reject", teavent_id=teavent_id),
    )
    builder.adjust(2)
    return builder.as_markup()
