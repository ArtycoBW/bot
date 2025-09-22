import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from .config import Settings
from .student_flow import router as student_router
from .admin_flow import router as admin_router


async def set_bot_commands(bot: Bot) -> None:
    """Показывает /start и /admin в меню Telegram."""
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить анкету"),
            # BotCommand(command="help", description="Помощь"),  # если нужно
        ]
    )


async def main():
    st = Settings()
    bot = Bot(
        st.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(student_router)
    dp.include_router(admin_router)

    # Установим команды в меню
    await set_bot_commands(bot)

    print("Шифу запущен...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
