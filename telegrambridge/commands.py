from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeDefault

user_commands = {
    "settings": "Show teavents settings",
    "teavents": "List upcoming teavents",
    "new": "Add new schedule",
}


async def set_default_commands(bot: Bot) -> None:
    await remove_default_commands(bot)

    await bot.set_my_commands(
        [
            BotCommand(command=command, description=description)
            for command, description in user_commands.items()
        ],
        scope=BotCommandScopeDefault(),
    )


async def remove_default_commands(bot: Bot) -> None:
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
