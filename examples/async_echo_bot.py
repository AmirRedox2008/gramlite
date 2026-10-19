"""Async echo bot — same logic as echo_bot.py, but on asyncio.

Run:  python examples/async_echo_bot.py   (requires aiohttp: pip install 'gramlite[async]')
"""

import asyncio
import logging

from gramlite import AsyncBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bot = AsyncBot("YOUR-BOT-TOKEN")


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message):
    await bot.reply_to(message, "Howdy! I am an async echo bot built with GramLite.")


@bot.message_handler(func=lambda message: True, content_types=["all"])
async def echo_all(message):
    await bot.reply_to(message, message.text or f"(got a {message.content_type})")


async def main():
    async with bot:  # ensures the aiohttp session is closed on exit
        await bot.infinity_polling()


if __name__ == "__main__":
    asyncio.run(main())
