import asyncio
import logging
import os

import aiogram
import aio_pika

from common.models import FlowUpdate
import telegrambridge.handlers as handlers
from telegrambridge.keyboards import get_regpoll_keyboard
from telegrambridge.middlewares import (
    CalendarMiddleware,
    QueueMiddleware,
    RpcMiddleware,
    init_aiogoogle,
)


async def process_update(bot: aiogram.Bot, update: FlowUpdate):
    match update.type:
        case "Poll open":
            for chat_id in update.communication_ids:
                await bot.send_message(
                    chat_id=chat_id,
                    text=update.type,
                    reply_markup=get_regpoll_keyboard(),
                )
        case _:
            for chat_id in update.communication_ids:
                await bot.send_message(chat_id=chat_id, text=update.type)


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq")
    aiogoogle = init_aiogoogle()
    async with connection, aiogoogle:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=0)

        teavents_q = await channel.declare_queue("teavents", durable=True)
        outgoing_updates_q = await channel.declare_queue(
            "outgoing_updates", durable=True
        )

        # TODO: use pydantic_settings to configure
        bot = aiogram.Bot(token=os.getenv("TOKEN"))
        dp = aiogram.Dispatcher()

        async def on_outgoing_update(message: aio_pika.abc.AbstractIncomingMessage):
            await process_update(bot, FlowUpdate.from_message(message))

        logging.info("Register consumers")
        await outgoing_updates_q.consume(on_outgoing_update, no_ack=True)

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

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
