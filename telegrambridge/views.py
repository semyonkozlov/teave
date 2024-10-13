from abc import ABC, abstractmethod
import asyncio
from contextlib import suppress
from datetime import datetime, timedelta

import aiogram
import humanize
from babel.dates import format_datetime
import motor.motor_asyncio as aio_mongo
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
    Italic,
)
from attr import define

from common.flow import TeaventFlow
from common.models import Teavent
from telegrambridge.keyboards import (
    make_plannedpoll_keyboard,
    make_regpoll_keyboard,
    make_started_keyboard,
)

humanize.i18n.activate("ru")


def format_location(location: str) -> Text:
    return as_key_value("Место", location)


def format_start(dt: datetime) -> Text:
    return as_key_value(
        "Начало", format_datetime(dt, "EEEE, d MMMM, HH:mm", locale="ru_RU")
    )


def format_duration(td: timedelta) -> Text:
    return as_key_value("Продолжительность", humanize.precisedelta(td, format="%0.0f"))


def format_participants(t: Teavent) -> Text:
    participants = t.effective_participant_ids or ["~"]
    return as_marked_section(
        f"Участники ({t.num_participants}/{t.config.max}, минимум {t.config.min}):",
        *participants,
        marker="  ",
    )


def format_reserve(t: Teavent) -> Text:
    reserve = t.reserve_participant_ids or ["~"]

    return as_marked_section(
        "Резерв:",
        *reserve,
        marker="  ",
    )


@define
class TeaventView(ABC):
    @abstractmethod
    def text(self, t: Teavent) -> Text: ...

    @abstractmethod
    def keyboard(self, t: Teavent): ...


class RegPollView(TeaventView):
    def text(self, t: Teavent) -> Text:
        return as_section(
            Bold(
                "✏️ ЗАПИСЬ НА СОБЫТИЕ ",
                TextLink(t.summary.upper(), url=t.link),
            ),
            "\n",
            as_list(
                format_location(t.location),
                format_start(t.start),
                format_duration(t.duration),
                "\n",
                format_participants(t),
                format_reserve(t),
            ),
        )

    def keyboard(self, t: Teavent):
        return make_regpoll_keyboard(t.id)


class PlannedView(TeaventView):
    def text(self, t: Teavent) -> Text:
        when = format_datetime(t.start, "d MMMM, в HH:mm", locale="ru_RU")
        return as_section(
            Bold(
                "✅ ",
                TextLink(t.summary.upper(), url=t.link),
                " СОСТОИТСЯ ",
                when.upper(),
            ),
            "\n",
            as_list(
                format_location(t.location),
                format_start(t.start),
                format_duration(t.duration),
                "\n",
                format_participants(t),
                format_reserve(t),
            ),
            "\n\n",
            Italic("Отказаться от участия можно только при наличии резерва"),
        )

    def keyboard(self, t: Teavent):
        return make_plannedpoll_keyboard(t.id)


class StartedView(TeaventView):
    def text(self, t: Teavent) -> Text:
        text = Text("Событие ", TextLink(t.summary, url=t.link), " началось")
        if t.latees:
            text = as_section(
                text, "\n", as_marked_section("Опаздывают:", *t.latees, marker="  ")
            )
        return text

    def keyboard(self, t: Teavent):
        return make_started_keyboard(t.id)


class CancelledView(TeaventView):
    def text(self, t: Teavent) -> Text:
        return Text("Событие ", TextLink(t.summary, url=t.link), Bold(" ОТМЕНЕНО"))

    def keyboard(self, t: Teavent):
        return None


@define
class TeaventPresenter:
    _bot: aiogram.Bot

    _client: aio_mongo.AsyncIOMotorClient
    _db_name: str

    # TODO try to replace with MongoDB transaction
    _update_lock = asyncio.Lock()

    _state_to_view = {
        TeaventFlow.poll_open.value: RegPollView(),
        TeaventFlow.planned.value: PlannedView(),
        TeaventFlow.started.value: StartedView(),
        TeaventFlow.cancelled.value: CancelledView(),
    }

    async def handle_update(self, teavent: Teavent):
        async with self._update_lock:
            await self._handle_update(teavent, lock=self._update_lock)

    async def _handle_update(self, teavent: Teavent, lock: asyncio.Lock):
        t2v = self._client.get_database(self._db_name).get_collection(
            "teavent_to_views"
        )

        if data := await t2v.find_one({"_id": teavent.id}):
            if data["state"] == teavent.state:
                await self._update(data["chat_message_ids"], teavent)
            else:
                await self._unpin(data["chat_message_ids"])
                with suppress(TelegramBadRequest):
                    await self._clear_markup(data["chat_message_ids"])

                chat_message_ids = await self._show(teavent)
                await self._pin(chat_message_ids)
                await t2v.update_one(
                    filter={"_id": teavent.id},
                    update={
                        "$set": {
                            "state": teavent.state,
                            "chat_message_ids": chat_message_ids,
                        }
                    },
                )

        else:
            chat_message_ids = await self._show(teavent)
            await self._pin(chat_message_ids)
            await t2v.insert_one(
                {
                    "_id": teavent.id,
                    "state": teavent.state,
                    "chat_message_ids": chat_message_ids,
                },
            )

    async def _show(self, teavent: Teavent):
        chat_message_ids = []

        if view := self._get_view(teavent.state):
            for chat_id in teavent.communication_ids:
                message = await self._bot.send_message(
                    chat_id=chat_id,
                    disable_web_page_preview=True,
                    # the order of following parameters MATTERS
                    reply_markup=view.keyboard(teavent),
                    **view.text(teavent).as_kwargs(),
                )
                chat_message_ids.append((chat_id, str(message.message_id)))

        return chat_message_ids

    async def _update(self, chat_message_ids: list, teavent: Teavent):
        view = self._get_view(teavent.state)
        assert view, "we should have view if we are trying to update something"

        for chat_id, message_id in chat_message_ids:
            with suppress(TelegramBadRequest):
                await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    disable_web_page_preview=True,
                    reply_markup=view.keyboard(teavent),
                    **view.text(teavent).as_kwargs(),
                )

    async def _pin(self, chat_message_ids: list):
        for chat_id, message_id in chat_message_ids:
            await self._bot.pin_chat_message(chat_id, message_id)

    async def _unpin(self, chat_message_ids: list):
        for chat_id, message_id in chat_message_ids:
            await self._bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)

    async def _clear_markup(self, chat_message_ids: list):
        for chat_id, message_id in chat_message_ids:
            await self._bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )

    def _get_view(self, state: str) -> TeaventView | None:
        return self._state_to_view.get(state)


def _render_teavent(t: Teavent) -> Text:
    participants = t.effective_participant_ids or ["~"]

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
