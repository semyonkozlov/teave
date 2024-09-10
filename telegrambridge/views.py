from abc import ABC, abstractmethod
from contextlib import suppress

import aiogram
from aiogram.exceptions import TelegramBadRequest
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

from common.models import Teavent
from telegrambridge.keyboards import make_regpoll_keyboard


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
    def text(self, teavent: Teavent) -> Text: ...

    @abstractmethod
    def keyboard(self, teavent: Teavent): ...


class RegPollView(TgStateView):
    def text(self, teavent: Teavent) -> Text:
        t = teavent
        participants = t.participant_ids or ["~"]

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
            )
        )
        # fmt: on

    def keyboard(self, teavent: Teavent):
        return make_regpoll_keyboard(teavent.id)


@define
class TgStateViewFactory:
    _bot: aiogram.Bot

    _state_to_view = {
        "poll_open": RegPollView,
        "created": TgStateView,
    }

    def create_view(self, state: str) -> TgStateView:
        return self._state_to_view[state](self._bot)


def _render_teavent(t: Teavent) -> Text:
    participants = as_list(*t.participant_ids) if t.participant_ids else ""

    # fmt: off
    return as_section(
        TextLink(t.summary, url=t.link),
        as_list(
            as_key_value("Статус", t.state),
            as_key_value("Начало", t.start),
            as_key_value("Продолжительность", t.duration),
            as_key_value("Участники", participants),
        )
    )
    # fmt: on


def render_teavents(teavents: list[Teavent]) -> Text:
    # fmt: off
    return as_section(
        Bold(Underline("БЛИЖАЙШИЕ СОБЫТИЯ")),
        "\n",
        as_list(
            *(_render_teavent(t) for t in teavents),
            sep="\n\n",
        )
    )
    # fmt: on
