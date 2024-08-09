import aiogram


class IsAdmin(aiogram.filters.BaseFilter):
    ADMINS = [933372142]

    async def __call__(self, message: aiogram.types.Message) -> bool:
        return message.from_user.id in self.ADMINS
