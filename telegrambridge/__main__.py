import asyncio
import logging
import os

import aiormq
import aiogram

from common.models import FlowUpdate
import telegrambridge.handlers as handlers
from telegrambridge.middlewares import AsyncQueue


async def main():
    logging.basicConfig(level=logging.INFO)

    connection = await aiormq.connect("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()
    await channel.basic_qos(prefetch_count=0)

    submits = await channel.queue_declare("submits", durable=True)
    user_updates = await channel.queue_declare("user_updates", durable=True)
    em_updates = await channel.queue_declare("em_updates", durable=True)

    # TODO: use pydantic_settings to configure
    bot = aiogram.Bot(token=str(os.getenv("TOKEN")))
    dp = aiogram.Dispatcher()

    async def on_em_update(message: aiormq.abc.DeliveredMessage):
        update = FlowUpdate.model_validate_json(message.body.decode())
        await bot.send_message(chat_id=update.chat_id, text=update.type)
        await channel.basic_ack(message.delivery_tag)

    await channel.basic_consume(em_updates.queue, on_em_update)

    dp.include_router(handlers.router)
    dp.message.middleware(AsyncQueue(channel, submits.queue))
    dp.message.middleware(AsyncQueue(channel, user_updates.queue))

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
