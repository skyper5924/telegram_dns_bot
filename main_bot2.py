import asyncio
import logging
import subprocess
import json
from aiogram import Bot, Dispatcher, html, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from settings import TOKEN, ADMIN

# Настройка логирования
logging.basicConfig(
    filename="bot_usage.log",
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Telegram ID для обратной связи
ADMIN_ID = ADMIN

# Инициализация диспетчера
dp = Dispatcher()

def get_main_keyboard():
    """
    Создает основную клавиатуру с кнопками.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Проверить домен")],
            [KeyboardButton(text="Обратная связь")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Этот хендлер обрабатывает сообщения с командой `/start`
    """
    keyboard = get_main_keyboard()
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}! Выберите действие:",
        reply_markup=keyboard
    )

async def run_dnstwist(domain: str) -> list:
    """
    Запуск скрипта dnstwist.py и возврат результата в формате JSON.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            "python", "dnstwist.py", "-r", "-w", domain, "-f", "json", "-t", "1000",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            return [f"Ошибка: {stderr.decode().strip()}"]

        return json.loads(stdout.decode().strip())
    except Exception as e:
        return [f"Не удалось запустить dnstwist.py: {e}"]

async def format_results(results: list) -> str:
    """
    Форматирование результатов анализа dnstwist.
    """
    if isinstance(results, list):
        formatted = [f"{item['domain']}, Создан: {item.get('whois_created', 'N/A')}" for item in results if 'domain' in item]
        return "\n".join(formatted)
    return "\n".join(results)

async def send_long_message(chat_id: int, text: str, bot: Bot) -> None:
    """
    Отправка длинных сообщений в Telegram частями.
    """
    limit = 4096  # Лимит символов в сообщении Telegram
    for i in range(0, len(text), limit):
        await bot.send_message(chat_id=chat_id, text=text[i:i+limit])

@dp.message()
async def handle_message(message: Message) -> None:
    """
    Обработка сообщений для анализа доменов или обратной связи.
    """
    keyboard = get_main_keyboard()

    if message.text == "Проверить домен":
        await message.answer("Введите доменное имя для анализа:", reply_markup=keyboard)

    elif message.text == "Обратная связь":
        await message.answer("Пожалуйста, отправьте ваше сообщение, и я передам его администратору.", reply_markup=types.ForceReply())

    elif message.reply_to_message and "Пожалуйста, отправьте ваше сообщение" in message.reply_to_message.text:
        # Обработка обратной связи
        logger.info(f"Обратная связь от {message.from_user.full_name} (@{message.from_user.username}): {message.text}")
        await message.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Новое сообщение от {message.from_user.full_name} (@{message.from_user.username}):\n\n{message.text}"
        )
        await message.answer("Спасибо за вашу обратную связь!", reply_markup=keyboard)
    else:
        # Обработка доменов
        domain = message.text.strip()
        if not domain:
            await message.answer("Пожалуйста, введите корректное доменное имя.", reply_markup=keyboard)
            return

        logger.info(f"Запрос анализа домена от {message.from_user.full_name} (@{message.from_user.username}): {domain}")
        await message.answer("Выполняю поиск, пожалуйста, подождите...", reply_markup=keyboard)

        results = await run_dnstwist(domain)
        formatted_results = await format_results(results)

        await send_long_message(
            chat_id=message.chat.id,
            text=f"Результат анализа для: {html.bold(domain)}:\n{formatted_results}",
            bot=message.bot
        )

async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print("Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
