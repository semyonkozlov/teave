import json
import datetime
from datetime import datetime

from attr import define
import aiogram
from aiogoogle import GoogleAPI, Aiogoogle
from aiogoogle.auth.creds import ServiceAccountCreds


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
