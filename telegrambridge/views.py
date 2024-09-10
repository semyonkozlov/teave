from abc import ABC, abstractmethod
from contextlib import suppress

import aiogram
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.formatting import Text
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
        return Text(teavent.state)

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
