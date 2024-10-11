from abc import ABC, abstractmethod
import asyncio
from contextlib import suppress

import aiogram
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
class TeaventView(ABC):
    @abstractmethod
    def text(self, t: Teavent) -> Text: ...

    @abstractmethod
    def keyboard(self, t: Teavent): ...


class RegPollView(TeaventView):
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


class PlannedView(TeaventView):
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
                await self._cleanup(data["chat_message_ids"])
                chat_message_ids = await self._show(teavent)
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
                    # the order of following parameters MATTERS
                    reply_markup=view.keyboard(teavent),
                    **view.text(teavent).as_kwargs(),
                )
                message_id = str(message.message_id)
                await self._bot.pin_chat_message(chat_id, message_id)
                chat_message_ids.append((chat_id, message_id))

        return chat_message_ids

    async def _update(self, chat_message_ids: list, teavent: Teavent):
        view = self._get_view(teavent.state)
        assert view, "we should have view if we are trying to update something"

        for chat_id, message_id in chat_message_ids:
            with suppress(TelegramBadRequest):
                await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=view.keyboard(teavent),
                    **view.text(teavent).as_kwargs(),
                )

    async def _cleanup(self, chat_message_ids: list):
        for chat_id, message_id in chat_message_ids:
            await self._bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
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
