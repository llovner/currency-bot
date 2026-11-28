import telebot
from telebot import types
import requests
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Нет токена! Создай файл .env со строкой TELEGRAM_BOT_TOKEN=...")

bot = telebot.TeleBot(BOT_TOKEN)

API_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
POPULAR = ["USD", "EUR", "CNY"]
CACHE = {"data": None, "time": 0}
CACHE_SECONDS = 600  # 10 минут


# ---------- Получение курсов (с кешем) ----------

def get_rates():
    """Возвращает словарь валют с ЦБ РФ. Держит данные 10 минут в памяти."""
    import time
    now = time.time()
    if CACHE["data"] is not None and now - CACHE["time"] < CACHE_SECONDS:
        return CACHE["data"]
    try:
        r = requests.get(API_URL, timeout=10)
        r.raise_for_status()
        data = r.json()["Valute"]
        CACHE["data"] = data
        CACHE["time"] = now
        return data
    except Exception:
        return CACHE["data"]  # если API упал — отдаём старые данные, они лучше ошибки


def get_rate_info(code):
    """Возвращает (текущий курс, вчерашний курс) или None."""
    data = get_rates()
    if not data or code not in data:
        return None
    val = data[code]
    rate = val["Value"] / val["Nominal"]
    prev = val["Previous"] / val["Nominal"]
    return rate, prev


# ---------- Клавиатура ----------

def rates_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(*[types.InlineKeyboardButton(f"💱 {code}", callback_data=f"rate_{code}") for code in POPULAR])
    return kb


def format_change(code):
    """Строка с динамикой курса: стрелка + изменение за сутки."""
    info = get_rate_info(code)
    if not info:
        return ""
    rate, prev = info
    diff = rate - prev
    arrow = "📈" if diff > 0 else ("📉" if diff < 0 else "➖")
    if diff == 0:
        return f"{arrow} Курс не изменился"
    word = "вырос" if diff > 0 else "упал"
    return f"{arrow} Курс {word} на {abs(diff):.2f} ₽ за сутки"


# ---------- Команды ----------

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я валютный бот 💱\n\n"
        "Напиши сумму и валюту, и я переведу в рубли.\n"
        "Например: `100 USD` или `50,5 EUR`\n\n"
        "Или выбери валюту кнопкой ниже 👇",
        parse_mode="Markdown",
        reply_markup=rates_keyboard(),
    )


@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(
        message.chat.id,
        "🤖 Что я умею:\n\n"
        "• `100 USD` — перевести сумму в рубли\n"
        "• Кнопки ниже — быстрый курс\n"
        "• Понимаю запятые: `99,9 EUR` тоже сработает\n\n"
        "Данные — официальные курсы ЦБ РФ, обновление раз в 10 минут.",
        parse_mode="Markdown",
        reply_markup=rates_keyboard(),
    )


# ---------- Кнопки ----------

@bot.callback_query_handler(func=lambda call: call.data.startswith("rate_"))
def rate_callback(call):
    code = call.data.replace("rate_", "")
    info = get_rate_info(code)
    if not info:
        bot.answer_callback_query(call.id, f"Не удалось получить курс {code}")
        return

    rate, prev = info
    text = f"💵 {code}: {rate:.2f} ₽\n{format_change(code)}"
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=rates_keyboard(),
    )
    bot.answer_callback_query(call.id)


# ---------- Конвертер (весь остальной текст) ----------

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text.strip().replace(",", ".")
    parts = text.split()

    if len(parts) < 2:
        bot.reply_to(
            message,
            "Напиши сумму и валюту, например: `100 USD`\n"
            "Или нажми кнопку ниже 👇",
            parse_mode="Markdown",
            reply_markup=rates_keyboard(),
        )
        return

    amount_str, code = parts[0], parts[1].upper()

    try:
        amount = float(amount_str)
    except ValueError:
        bot.reply_to(
            message,
            f"«{amount_str}» не похоже на число 🙂 Попробуй так: `100 USD`",
            parse_mode="Markdown",
        )
        return

    if amount <= 0:
        bot.reply_to(message, "Сумма должна быть больше нуля!")
        return

    info = get_rate_info(code)
    if not info:
        bot.reply_to(
            message,
            f"Не знаю валюту {code}. Попробуй USD, EUR, CNY, GBP или другой код валюты.",
        )
        return

    rate, _ = info
    result = amount * rate
    bot.reply_to(
        message,
        f"💵 {amount:g} {code} = {result:,.2f} ₽".replace(",", " ").replace(".", ",") + "\n"
        + format_change(code),
        reply_markup=rates_keyboard(),
    )


if __name__ == "__main__":
    print("Бот запущен!")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30)
        except Exception as e:
            print(f"Ошибка соединения: {e}. Перезапуск через 15 секунд...")
            import time
            time.sleep(15)
