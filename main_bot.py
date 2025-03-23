import asyncio
import logging
import subprocess
import json
from datetime import datetime
from pathlib import Path
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

STATS_FILE = "stats.json"

def load_stats() -> dict:
    """
    Загружает статистику из файла или возвращает пустую структуру, если файл не существует.
    """
    if Path(STATS_FILE).exists():
        with open(STATS_FILE, "r") as file:
            data = json.load(file)
            data["users"] = set(data.get("users", []))  # Преобразуем список обратно в множество
            return data
    return {"daily": 0, "monthly": 0, "users": set()}

def save_stats(stats: dict) -> None:
    """
    Сохраняет статистику в файл.
    """
    stats["users"] = list(stats["users"])  # Преобразуем множество в список для сохранения
    with open(STATS_FILE, "w") as file:
        json.dump(stats, file, indent=4)

def update_stats(user_id: int) -> None:
    """
    Обновляет статистику при новом запросе.
    """
    stats = load_stats()
    today = datetime.now().date()
    this_month = today.month

    if "last_update" not in stats or stats["last_update"] != str(today):
        stats["daily"] = 0
        stats["last_update"] = str(today)
    if "last_month" not in stats or stats["last_month"] != this_month:
        stats["monthly"] = 0
        stats["last_month"] = this_month

    stats["daily"] += 1
    stats["monthly"] += 1
    stats["users"].add(user_id)

    save_stats(stats)

def get_usage_stats() -> str:
    """
    Возвращает статистику из файла.
    """
    stats = load_stats()
    return (
        f"Статистика использования:\n"
        f"Запросов за сегодня: {stats['daily']}\n"
        f"Запросов за месяц: {stats['monthly']}\n"
        f"Уникальных пользователей: {len(stats['users'])}"
    )

def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    Создает основную клавиатуру с кнопками.
    Кнопка "Статистика использования" отображается только для администратора.
    """
    keyboard = [
        [KeyboardButton(text="Проверить домен")],
        [KeyboardButton(text="Обратная связь")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(text="Статистика использования")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Этот хендлер обрабатывает сообщения с командой `/start`
    """
    keyboard = get_main_keyboard(message.from_user.id)
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
            "python", "dnstwist.py", "-r", "-w", domain, "-f", "json", "-t", "5000",
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
        # Разделяем результаты на те, у которых есть дата, и те, у которых её нет
        with_date = [item for item in results if 'domain' in item and 'whois_created' in item and item['whois_created']]
        without_date = [item for item in results if
                        'domain' in item and ('whois_created' not in item or not item['whois_created'])]

        # Сортируем по дате создания (от новых к старым)
        sorted_with_date = sorted(with_date, key=lambda x: x['whois_created'], reverse=True)

        # Форматируем результат
        formatted = [f"{item['domain']}, Создан: {item['whois_created']}" for item in sorted_with_date]
        formatted += [f"{item['domain']}, Создан: N/A" for item in without_date]

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
    Обработка сообщений для анализа доменов, обратной связи и статистики.
    """
    keyboard = get_main_keyboard(message.from_user.id)

    if message.text == "Проверить домен":
        update_stats(message.from_user.id)
        await message.answer("Введите доменное имя для анализа:", reply_markup=keyboard)

    elif message.text == "Обратная связь":
        update_stats(message.from_user.id)
        await message.answer("Пожалуйста, отправьте ваше сообщение, и я передам его администратору.", reply_markup=types.ForceReply())

    elif message.text == "Статистика использования":
        if message.from_user.id == ADMIN_ID:
            stats = get_usage_stats()
            await message.answer(stats, reply_markup=keyboard)
        else:
            await message.answer("У вас нет прав для просмотра статистики.", reply_markup=keyboard)

    elif message.reply_to_message and "Пожалуйста, отправьте ваше сообщение" in message.reply_to_message.text:
        logger.info(f"Обратная связь от {message.from_user.full_name} (@{message.from_user.username}): {message.text}")
        await message.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Новое сообщение от {message.from_user.full_name} (@{message.from_user.username}):\n\n{message.text}"
        )
        await message.answer("Спасибо за вашу обратную связь!", reply_markup=keyboard)

    else:
        domain = message.text.strip()
        if not domain:
            await message.answer("Пожалуйста, введите корректное доменное имя.", reply_markup=keyboard)
            return

        update_stats(message.from_user.id)
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
