from collections.abc import Coroutine
import json
import datetime
from datetime import datetime

from attr import define
import pydantic
import aiogram
import aio_pika
from aiogoogle import GoogleAPI, Aiogoogle
from aiogoogle.auth.creds import ServiceAccountCreds

from common.pika_pydantic import ModelMessage


@define
class QueueMiddleware(aiogram.BaseMiddleware):
    _queue: aio_pika.abc.AbstractQueue

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data[self._queue.name] = self
        return await handler(event, data)

    async def publish(self, msg: pydantic.BaseModel):
        await self._queue.channel.default_exchange.publish(
            ModelMessage(msg),
            routing_key=self._queue.name,
        )


@define
class RpcMiddleware(aiogram.BaseMiddleware):
    _method: Coroutine

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data[self._method.name] = self._method
        return await handler(event, data)


def init_aiogoogle() -> Aiogoogle:
    SERVICE_ACCOUNT_FILE = "telegrambridge/gcredentials.json"

    with open(SERVICE_ACCOUNT_FILE) as f:
        service_account_info = json.load(f)

    service_account_creds = ServiceAccountCreds(
        scopes=["https://www.googleapis.com/auth/calendar"], **service_account_info
    )

    return Aiogoogle(service_account_creds=service_account_creds)


@define
class CalendarMiddleware(aiogram.BaseMiddleware):
    _aiogoogle: Aiogoogle
    _calendar_api: GoogleAPI

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data["calendar"] = self
        return await handler(event, data)

    async def list_events(self, calendar_id: str):
        return await self._aiogoogle.as_service_account(
            self._calendar_api.events.list(
                calendarId=calendar_id,
                timeMin=datetime.utcnow().isoformat() + "Z",
            )
        )
