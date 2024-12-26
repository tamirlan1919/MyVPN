import asyncio
from aiogram import Bot, Dispatcher, types
import logging
from handlers import router

logging.basicConfig(level=logging.INFO)
bot = Bot('token')
dp = Dispatcher()
dp.include_router(router)

async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())