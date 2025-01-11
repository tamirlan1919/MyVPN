import asyncio
from aiogram import Bot, Dispatcher, types
import logging
from handlers import router
from config.config import TELEGRAM_TOKEN
logging.basicConfig(level=logging.INFO)
bot = Bot(TELEGRAM_TOKEN)
dp = Dispatcher()
dp.include_router(router)

async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())