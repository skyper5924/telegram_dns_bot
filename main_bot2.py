import asyncio
import logging
import subprocess
import json
#from os import getenv

from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from settings import TOKEN

# Настройка логирования
logging.basicConfig(
    filename="bot_usage.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Bot token can be obtained via https://t.me/BotFather
#TOKEN = getenv("BOT_TOKEN")

# All handlers should be attached to the Router (or Dispatcher)

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    await message.answer(f"Привет, {html.bold(message.from_user.full_name)}! Отправь мне доменное имя, и я его проанализирую.")

async def run_dnstwist(domain: str) -> list:
    """
    Run the dnstwist.py script and return its parsed JSON output.
    """
    try:
        # Call the dnstwist.py script with the given domain
        process = await asyncio.create_subprocess_exec(
            "python", "dnstwist.py", "-r", "-w", domain, "-f", "json", "-t", "1000",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return [f"Error: {stderr.decode().strip()}"]

        return json.loads(stdout.decode().strip())
    except Exception as e:
        return [f"Failed to run dnstwist.py: {e}"]

async def format_results(results: list) -> str:
    """
    Extract and format domain and whois_created from dnstwist results.
    """
    if isinstance(results, list):
        formatted = [f"{item['domain']}, Создан: {item.get('whois_created', 'N/A')}" for item in results if 'domain' in item]
        return "\n".join(formatted)
    return "\n".join(results)

async def send_long_message(chat_id: int, text: str, bot: Bot) -> None:
    """
    Split a long message into parts and send them separately.
    """
    limit = 4096  # Telegram message character limit
    for i in range(0, len(text), limit):
        await bot.send_message(chat_id=chat_id, text=text[i:i+limit])

@dp.message()
async def domain_handler(message: Message) -> None:
    """
    Handle domain analysis requests.
    """
    domain = message.text.strip()
    if not domain:
        await message.answer("Пожалуйста введите корректное доменное имя.")
        return

    await message.answer("Выполняю поиск, пожалуйста, подождите...")

    # Run the dnstwist.py script and get the result
    results = await run_dnstwist(domain)

    # Format the results
    formatted_results = await format_results(results)

    # Send the result back to the user in parts if necessary
    await send_long_message(chat_id=message.chat.id, text=f"Результат анализа для:  {html.bold(domain)}:\n{formatted_results}", bot=message.bot)

async def main() -> None:
    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # And then run events dispatching
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

