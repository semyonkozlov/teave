from abc import ABC, abstractmethod
from contextlib import suppress

import aiogram
from aiogram.exceptions import TelegramBadRequest
from aiogram.types.message import Message
from aiogram.utils.formatting import (
    as_list,
    as_section,
    as_key_value,
    as_marked_section,
    TextLink,
    Bold,
    Text,
    Underline,
)

from attr import define

from common.flow import TeaventFlow
from common.models import Teavent
from telegrambridge.keyboards import (
    make_plannedpoll_keyboard,
    make_regpoll_keyboard,
    make_started_keyboard,
)


@define
class TgStateView(ABC):
    _bot: aiogram.Bot

    async def show(self, teavent: Teavent):
        for chat_id in teavent.communication_ids:
            await self._bot.send_message(
                chat_id=chat_id,
                **self.text(teavent).as_kwargs(),
                reply_markup=self.keyboard(teavent),
            )

    async def update(self, message: aiogram.types.Message, teavent: Teavent):
        with suppress(TelegramBadRequest):
            await message.edit_text(
                **self.text(teavent).as_kwargs(),
                reply_markup=self.keyboard(teavent),
            )

    @abstractmethod
    def text(self, t: Teavent) -> Text: ...

    @abstractmethod
    def keyboard(self, t: Teavent): ...


class NoOpView(TgStateView):
    async def show(self, teavent: Teavent):
        pass

    async def update(self, message: Message, teavent: Teavent):
        pass

    def text(self, t: Teavent) -> Text:
        return NotImplemented

    def keyboard(self, t: Teavent):
        return NotImplemented


class RegPollView(TgStateView):
    def text(self, t: Teavent) -> Text:
        participants = t.effective_participant_ids or ["~"]
        reserve = t.reserve_participant_ids or ["~"]

        # fmt: off
        return as_section(
            Bold("ЗАПИСЬ НА СОБЫТИЕ ", TextLink(t.summary, url=t.link)),
            "\n",
            as_list(
                as_key_value("Место", t.location),
                as_key_value("Начало", t.start),
                as_key_value("Продолжительность", t.duration),
                as_marked_section(
                    f"Участники ({t.num_participants}/{t.config.max}):", 
                    *participants, 
                    marker="  "),
                as_marked_section(
                    "Резерв:", 
                    *reserve, 
                    marker="  "),
            )
        )
        # fmt: on

    def keyboard(self, t: Teavent):
        return make_regpoll_keyboard(t.id)


class PlannedView(TgStateView):
    def text(self, t: Teavent) -> Text:
        participants = t.effective_participant_ids or ["~"]
        reserve = t.reserve_participant_ids or ["~"]

        # fmt: off
        return as_section(
            Bold(TextLink(t.summary, url=t.link), f" состоится {t.start.date()} в {t.start.time()}"),
            "\n",
            as_list(
                as_key_value("Место", t.location),
                as_key_value("Продолжительность", t.duration),
                as_marked_section(
                    f"Участники ({t.num_participants}/{t.config.max}):", 
                    *participants, 
                    marker="  "),
                as_marked_section(
                    "Резерв:", 
                    *reserve, 
                    marker="  "),
            )
        )
        # fmt: on

    def keyboard(self, t: Teavent):
        return make_plannedpoll_keyboard(t.id)


class StartedView(TgStateView):
    def text(self, t: Teavent) -> Text:
        text = Text("Событие ", TextLink(t.summary, url=t.link), " началось")
        if t.latees:
            text = as_section(
                text, "\n", as_marked_section("Опаздывают:", *t.latees, marker="  ")
            )
        return text

    def keyboard(self, t: Teavent):
        return make_started_keyboard(t.id)


@define
class TgStateViewFactory:
    _bot: aiogram.Bot

    _state_to_view = {
        TeaventFlow.poll_open.value: RegPollView,
        TeaventFlow.planned.value: PlannedView,
        TeaventFlow.started.value: StartedView,
    }

    def create_view(self, state: str) -> TgStateView:
        view_cls = self._state_to_view.get(state) or NoOpView
        return view_cls(self._bot)


def _render_teavent(t: Teavent) -> Text:
    participants = t.effective_participant_ids or ["~"]

    # fmt: off
    return as_section(
        TextLink(t.summary, url=t.link),
        as_list(
            as_key_value("Статус", t.state),
            as_key_value("Начало", t.start),
            as_key_value("Продолжительность", t.duration),
            as_marked_section(
                f"Участники ({t.num_participants}/{t.config.max}):", 
                *participants, 
                marker="  "),
        )
    )
    # fmt: on


def render_teavents(teavents: list[Teavent]) -> Text:
    teavents_list = [_render_teavent(t) for t in teavents] or ["~"]

    # fmt: off
    return as_section(
        Bold(Underline("БЛИЖАЙШИЕ СОБЫТИЯ")),
        "\n",
        as_list(
            *teavents_list,
            sep="\n\n",
        )
    )
    # fmt: on
