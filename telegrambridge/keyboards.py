from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

# TODO: TeaventAction base class


class RegPollAction(CallbackData, prefix="reg_poll"):
    action: str
    teavent_id: str


def make_regpoll_keyboard(teavent_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➕ Join",
        callback_data=RegPollAction(action="confirm", teavent_id=teavent_id),
    )
    builder.button(
        text="➖ Leave",
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
        text="➕ Join as reserve",
        callback_data=PlannedPollAction(action="confirm", teavent_id=teavent_id),
    )
    builder.button(
        text="➖ Leave",
        callback_data=PlannedPollAction(action="reject", teavent_id=teavent_id),
    )
    builder.adjust(2)
    return builder.as_markup()


class IAmLateAction(CallbackData, prefix="i_am_late"):
    teavent_id: str
    action: str


def make_started_keyboard(teavent_id: str):
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🏃 I am late",
        callback_data=IAmLateAction(action="i_am_late", teavent_id=teavent_id),
    )
    builder.adjust(1)
    return builder.as_markup()
