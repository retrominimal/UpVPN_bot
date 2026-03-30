"""
Главный файл бота
"""

import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import config
from database import db
from handlers import router
from admin import admin_router


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """При запуске бота"""
    await db.connect()
    logger.info("Database connected")
    
    # Устанавливаем вебхук
    await bot.set_webhook(
        url=config.WEBHOOK_URL,
        drop_pending_updates=True
    )
    logger.info(f"Webhook set to {config.WEBHOOK_URL}")


async def on_shutdown(bot: Bot):
    """При остановке бота"""
    await db.close()
    await bot.delete_webhook()
    logger.info("Bot stopped")


def main():
    """Запуск бота"""
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем роутеры
    dp.include_router(router)
    dp.include_router(admin_router)
    
    # Регистрируем startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Создаем aiohttp приложение
    app = web.Application()
    
    # Настраиваем webhook
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    )
    webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
    
    setup_application(app, dp, bot=bot)
    
    # Запускаем веб-сервер
    web.run_app(
        app,
        host=config.WEBAPP_HOST,
        port=config.WEBAPP_PORT
    )


if __name__ == "__main__":
    main()
