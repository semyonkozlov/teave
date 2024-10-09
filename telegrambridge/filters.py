import aiogram


class IsAdmin(aiogram.filters.BaseFilter):
    SUPERADMINS = [933372142]

    async def __call__(self, message: aiogram.types.Message, bot: aiogram.Bot) -> bool:
        if message.from_user.id in self.SUPERADMINS:
            return True

        chat_admins = await bot.get_chat_administrators(chat_id=message.chat.id)
        return any(admin.user.id == message.from_user.id for admin in chat_admins)
