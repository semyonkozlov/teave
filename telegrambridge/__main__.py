import asyncio
import logging
import os

from aiogram import Bot, Dispatcher

import telegrambridge.handlers as handlers
from telegrambridge.middlewares import RabbitMqChannel


async def main():
    logging.basicConfig(level=logging.INFO)

    # TODO: use pydantic settings to configure
    bot = Bot(token=str(os.getenv("TOKEN")))
    dp = Dispatcher()

    dp.message.middleware(RabbitMqChannel("rabbitmq"))

    dp.include_router(handlers.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
