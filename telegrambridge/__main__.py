import asyncio
import logging
import os

import aiogram
import aio_pika

from common.models import FlowUpdate
import telegrambridge.handlers as handlers
from telegrambridge.middlewares import QueueMiddleware, RpcMiddleware


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aio_pika.connect("amqp://guest:guest@rabbitmq/")
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=0)

        submits = await channel.declare_queue("submits", durable=True)
        user_updates = await channel.declare_queue("user_updates", durable=True)
        em_updates = await channel.declare_queue("em_updates", durable=True)

        # TODO: use pydantic_settings to configure
        bot = aiogram.Bot(token=str(os.getenv("TOKEN")))
        dp = aiogram.Dispatcher()

        async def on_em_update(message: aio_pika.abc.AbstractIncomingMessage):
            update = FlowUpdate.from_message(message)
            await bot.send_message(chat_id=update.chat_id, text=update.type)

        logging.info("Register consumers")
        await em_updates.consume(on_em_update, no_ack=True)

        logging.info("Create RPC-client")
        rpc = await aio_pika.patterns.RPC.create(channel)

        logging.info("Set up bot handlers")
        dp.include_router(handlers.router)
        dp.message.middleware(QueueMiddleware(submits))
        dp.message.middleware(QueueMiddleware(user_updates))
        dp.message.middleware(RpcMiddleware(rpc.proxy.list_events))

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
