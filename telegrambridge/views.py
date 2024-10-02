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
from aiogram.utils.deep_linking import create_deep_link
from attr import define

from common.flow import TeaventFlow
from common.models import Teavent
from telegrambridge.keyboards import (
    make_plannedpoll_keyboard,
    make_regpoll_keyboard,
    make_started_keyboard,
)


@define
class TgTeaventView(ABC):
    _bot: aiogram.Bot

    async def show(self, teavent: Teavent):
        for chat_id in teavent.communication_ids:
            await self._bot.send_message(
                chat_id=chat_id,
                # the order of following parameters MATTERS
                reply_markup=self.keyboard(teavent),
                **self.text(teavent).as_kwargs(),
            )

    async def update(self, message: aiogram.types.Message, teavent: Teavent):
        with suppress(TelegramBadRequest):
            await message.edit_text(
                reply_markup=self.keyboard(teavent),
                **self.text(teavent).as_kwargs(),
            )

    @abstractmethod
    def text(self, t: Teavent) -> Text: ...

    @abstractmethod
    def keyboard(self, t: Teavent): ...


class NoOpView(TgTeaventView):
    async def show(self, teavent: Teavent):
        pass

    async def update(self, message: Message, teavent: Teavent):
        pass

    def text(self, t: Teavent) -> Text:
        return NotImplemented

    def keyboard(self, t: Teavent):
        return NotImplemented


class RegPollView(TgTeaventView):
    def text(self, t: Teavent) -> Text:
        participants = t.effective_participant_ids or ["~"]
        reserve = t.reserve_participant_ids or ["~"]

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
                    marker="  ",
                ),
                as_marked_section(
                    "Резерв:",
                    *reserve,
                    marker="  ",
                ),
            ),
        )

    def keyboard(self, t: Teavent):
        return make_regpoll_keyboard(t.id)


class PlannedView(TgTeaventView):
    def text(self, t: Teavent) -> Text:
        participants = t.effective_participant_ids or ["~"]
        reserve = t.reserve_participant_ids or ["~"]

        return as_section(
            Bold(
                TextLink(t.summary, url=t.link),
                f" состоится {t.start.date()} в {t.start.time()}",
            ),
            "\n",
            as_list(
                as_key_value("Место", t.location),
                as_key_value("Продолжительность", t.duration),
                as_marked_section(
                    f"Участники ({t.num_participants}/{t.config.max}):",
                    *participants,
                    marker="  ",
                ),
                as_marked_section("Резерв:", *reserve, marker="  "),
            ),
        )

    def keyboard(self, t: Teavent):
        return make_plannedpoll_keyboard(t.id)


class StartedView(TgTeaventView):
    def text(self, t: Teavent) -> Text:
        text = Text("Событие ", TextLink(t.summary, url=t.link), " началось")
        if t.latees:
            text = as_section(
                text, "\n", as_marked_section("Опаздывают:", *t.latees, marker="  ")
            )
        return text

    def keyboard(self, t: Teavent):
        return make_started_keyboard(t.id)


class CancelledView(TgTeaventView):
    def text(self, t: Teavent) -> Text:
        return Text("Событие ", TextLink(t.summary, url=t.link), Bold(" ОТМЕНЕНО"))

    def keyboard(self, t: Teavent):
        return None


@define
class TgTeaventViewFactory:
    _bot: aiogram.Bot

    _state_to_view = {
        TeaventFlow.poll_open.value: RegPollView,
        TeaventFlow.planned.value: PlannedView,
        TeaventFlow.started.value: StartedView,
        TeaventFlow.cancelled.value: CancelledView,
    }

    def create_view(self, state: str) -> TgTeaventView:
        view_cls = self._state_to_view.get(state) or NoOpView
        return view_cls(self._bot)


def _render_teavent(t: Teavent) -> Text:
    participants = t.effective_participant_ids or ["~"]
    # TODO move 'teave_bot' to settings
    cancel_deep_link = create_deep_link(
        username="teave_bot", link_type="start", payload=f"cancel_{t.id}"
    )

    return as_section(
        TextLink(t.summary, url=t.link),
        as_list(
            Text(f"/settings_{t.id}"),
            as_key_value("Статус", t.state),
            as_key_value("Начало", t.start),
            as_key_value("Продолжительность", t.duration),
            as_marked_section(
                f"Участники ({t.num_participants}/{t.config.max}):",
                *participants,
                marker="  ",
            ),
        ),
    )


def render_teavents(teavents: list[Teavent]) -> Text:
    teavents_list = [_render_teavent(t) for t in teavents] or ["~"]

    return as_section(
        Bold(Underline("БЛИЖАЙШИЕ СОБЫТИЯ")),
        "\n",
        as_list(
            *teavents_list,
            sep="\n\n",
        ),
    )
