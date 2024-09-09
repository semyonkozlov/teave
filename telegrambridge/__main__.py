import asyncio
import logging
import os

import aiogram
import motor.motor_asyncio as aio_mongo
import aio_pika

from common.models import FlowUpdate, Teavent
import telegrambridge.handlers as handlers
from telegrambridge.keyboards import get_regpoll_keyboard
from telegrambridge.middlewares import (
    CalendarMiddleware,
    QueueMiddleware,
    RpcMiddleware,
    init_aiogoogle,
)


async def process_teavent_update(teavent: Teavent, bot: aiogram.Bot):
    match teavent.state:
        case "poll_open":
            for chat_id in teavent.communication_ids:
                await bot.send_message(
                    chat_id=chat_id,
                    text=teavent.state,
                    reply_markup=get_regpoll_keyboard(teavent.id),
                )
            ...


async def main():
    logging.basicConfig(level=logging.INFO)

    rmq_connection = await aio_pika.connect("amqp://guest:guest@rabbitmq")
    mongoc = aio_mongo.AsyncIOMotorClient("mongodb://admin:pass@mongodb")
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
        dp = aiogram.Dispatcher()

        async def on_teavent_update(message: aio_pika.abc.AbstractIncomingMessage):
            await process_teavent_update(Teavent.from_message(message), bot)

        logging.info("Register consumers")
        await outgoing_updates_q.consume(on_teavent_update, no_ack=True)

        logging.info("Create RPC-client")
        rpc = await aio_pika.patterns.RPC.create(channel)

        logging.info("Discover Google Calendar API")
        calendar_api = await aiogoogle.discover("calendar", "v3")

        logging.info("Set up bot handlers")
        dp.include_router(handlers.router)

        logging.info("Init middlewares")
        dp.message.middleware(QueueMiddleware(teavents_q))
        dp.message.middleware(RpcMiddleware(rpc.proxy.list_teavents))
        dp.message.middleware(RpcMiddleware(rpc.proxy.user_action))
        dp.message.middleware(CalendarMiddleware(aiogoogle, calendar_api))

        dp.callback_query.middleware(RpcMiddleware(rpc.proxy.user_action))

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
