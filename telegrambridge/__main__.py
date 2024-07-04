import asyncio
import logging
import os

import aiogram
import aio_pika

from common.models import FlowUpdate
import telegrambridge.handlers as handlers
from telegrambridge.middlewares import QueueMiddleware


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
            update = FlowUpdate.model_validate_json(message.body.decode())
            await bot.send_message(chat_id=update.chat_id, text=update.type)
            await message.ack()

        await em_updates.consume(on_em_update)

        dp.include_router(handlers.router)
        dp.message.middleware(QueueMiddleware(submits))
        dp.message.middleware(QueueMiddleware(user_updates))

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
