import asyncio
import logging
import os

import aiogram
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.mongo import MongoStorage
import aiogram_dialog
import aio_pika
import motor.motor_asyncio as aio_mongo

from common.models import Teavent
from telegrambridge.commands import set_default_commands
import telegrambridge.handlers as handlers
import telegrambridge.dialogs as dialogs
from telegrambridge.middlewares import CalendarMiddleware, init_aiogoogle
from telegrambridge.views import TgTeaventViewFactory


async def main():
    logging.basicConfig(level=logging.INFO)

    rmq_connection = await aio_pika.connect("amqp://guest:guest@rabbitmq")
    mongoc = aio_mongo.AsyncIOMotorClient("mongodb://admin:pass@mongodb")
    aiogoogle = init_aiogoogle()

    async with rmq_connection, aiogoogle:
        channel = await rmq_connection.channel()
        await channel.set_qos(prefetch_count=0)

        outgoing_updates_q = await channel.declare_queue(
            "outgoing_updates", durable=True
        )

        # TODO: use pydantic_settings to configure
        bot = aiogram.Bot(token=os.getenv("TOKEN"))

        logging.info("Set commands menu")
        await set_default_commands(bot)

        logging.info("Init views")
        view_factory = TgTeaventViewFactory(bot)

        async def on_teavent_update(message: aio_pika.abc.AbstractIncomingMessage):
            teavent = Teavent.from_message(message)
            await view_factory.create_view(teavent.state).show(teavent)

        logging.info("Register consumers")
        await outgoing_updates_q.consume(on_teavent_update, no_ack=True)

        logging.info("Create RPC-client")
        rpc = await aio_pika.patterns.RPC.create(channel)

        logging.info("Discover Google Calendar API")
        calendar_api = await aiogoogle.discover("calendar", "v3")

        dp = aiogram.Dispatcher(
            storage=MongoStorage(
                mongoc, key_builder=DefaultKeyBuilder(with_destiny=True)
            ),
            view_factory=view_factory,
            list_teavents=rpc.proxy.list_teavents,
            get_teavent=rpc.proxy.get_teavent,
            manage_teavent=rpc.proxy.manage_teavent,
            user_action=rpc.proxy.user_action,
            tasks=rpc.proxy.tasks,
        )

        logging.info("Set up dialogs")
        aiogram_dialog.setup_dialogs(dp)
        dp.include_router(dialogs.admin_dialog())
        dp.include_router(dialogs.new_teavents_dialog())

        logging.info("Set up bot handlers")
        dp.include_router(handlers.router)

        logging.info("Init middlewares")
        dp.message.middleware(CalendarMiddleware(aiogoogle, calendar_api))

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
