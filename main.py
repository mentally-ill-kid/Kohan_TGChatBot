import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from handlers import router
from database import init_db

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    # Проверка наличия токена
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден! Проверьте .env файл.")
        return
    
    bot = None
    try:
        await init_db()
        logger.info("База данных инициализирована")

        bot = Bot(token=BOT_TOKEN)
        dp = Dispatcher()
        dp.include_router(router)

        logger.info("Бот запущен и ждёт сообщений...")
        await dp.start_polling(bot)
    
    except Exception as e:
        logger.exception(f"Критическая ошибка при запуске бота: {e}")
    finally:
        if bot:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
