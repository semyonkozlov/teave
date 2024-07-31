from collections.abc import Awaitable
import json

import pydantic
import aiogram
import aio_pika
from aiogoogle import GoogleAPI, Aiogoogle
from aiogoogle.auth.creds import ServiceAccountCreds

from common.pika_pydantic import ModelMessage


class QueueMiddleware(aiogram.BaseMiddleware):
    def __init__(self, queue: aio_pika.abc.AbstractQueue):
        self._queue = queue

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data[self._queue.name] = self
        return await handler(event, data)

    async def publish(self, msg: pydantic.BaseModel):
        await self._queue.channel.default_exchange.publish(
            ModelMessage(msg),
            routing_key=self._queue.name,
        )


class RpcMiddleware(aiogram.BaseMiddleware):
    def __init__(self, rpc_method: Awaitable):
        self._method = rpc_method

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


class CalendarMiddleware(aiogram.BaseMiddleware):
    def __init__(self, aiogoogle: Aiogoogle, calendar_api: GoogleAPI):
        self._aiogoogle = aiogoogle
        self._calendar_api = calendar_api

    async def __call__(self, handler, event: aiogram.types.Message, data: dict):
        data["calendar"] = self
        return await handler(event, data)

    async def list_events(self, calendar_id: str):
        return await self._aiogoogle.as_service_account(
            self._calendar_api.events.list(
                calendarId=calendar_id,
            )
        )
