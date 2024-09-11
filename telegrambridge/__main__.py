import asyncio
import logging
import os

import aiogram
import aio_pika

from common.models import Teavent
import telegrambridge.handlers as handlers
from telegrambridge.middlewares import (
    CalendarMiddleware,
    RmqMiddleware,
    init_aiogoogle,
)
from telegrambridge.views import TgStateViewFactory


async def main():
    logging.basicConfig(level=logging.INFO)

    rmq_connection = await aio_pika.connect("amqp://guest:guest@rabbitmq")
    aiogoogle = init_aiogoogle()

    async with rmq_connection, aiogoogle:
        channel = await rmq_connection.channel()
        await channel.set_qos(prefetch_count=0)

        teavents_q = await channel.declare_queue("teavents", durable=True)
        outgoing_updates_q = await channel.declare_queue(
            "outgoing_updates", durable=True
        )

        # TODO: use pydantic_settings to configure
        bot = aiogram.Bot(token=os.getenv("TOKEN"))

        logging.info("Init views")
        view_factory = TgStateViewFactory(bot)

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
            view_factory=view_factory,
            user_action=rpc.proxy.user_action,
            list_teavents=rpc.proxy.list_teavents,
        )

        logging.info("Set up bot handlers")
        dp.include_router(handlers.router)

        logging.info("Init middlewares")
        dp.message.middleware(RmqMiddleware(teavents_q))
        dp.message.middleware(CalendarMiddleware(aiogoogle, calendar_api))

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
