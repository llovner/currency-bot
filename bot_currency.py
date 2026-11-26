import telebot
from telebot import types
import requests
import os
import time
import re
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Нет токена! Создай файл .env со строкой TELEGRAM_BOT_TOKEN=...")

bot = telebot.TeleBot(BOT_TOKEN)

CURRENCIES = {
    "USD": "Доллар США",
    "EUR": "Евро",
    "GBP": "Фунт стерлингов",
    "CNY": "Юань",
    "JPY": "Иена",
    "AED": "Дирхам ОАЭ",
}

cache = {"data": None, "time": 0}

def get_rates():
    if cache["data"] is not None and time.time() - cache["time"] < 600:
        return cache["data"]
    try:
        r = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        r.raise_for_status()
        data = r.json()
        cache["data"] = data
        cache["time"] = time.time()
        return data
    except Exception:
        return None

def rate_text(code):
    data = get_rates()
    if not data:
        return "⚠️ Не удалось получить курсы. Попробуй позже."
    val = data["Valute"].get(code)
    if not val:
        return f"Валюта {code} не найдена."
    course = val["Value"] / val["Nominal"]
    diff = val["Value"] - val["Previous"]
    arrow = "📈 +" if diff > 0 else ("📉 " if diff < 0 else "➖ ")
    change = f"{arrow}{abs(diff / val['Nominal']):.2f} ₽ за сутки"
    date = data["Date"][:10]
    return (
        f"{val['Name']} ({code})\n"
        f"Курс ЦБ РФ: **{course:.2f} ₽**\n"
        f"{change}\n"
        f"Данные на {date}"
    )

def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=3)
    buttons = [types.InlineKeyboardButton(code, callback_data=f"rate:{code}") for code in CURRENCIES]
    kb.add(*buttons)
    return kb

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Привет! Я бот курсов валют 💱\n\n"
        "Нажми на кнопку ниже или напиши /help, чтобы узнать команды.",
        reply_markup=main_menu(),
    )

@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "🤖 Я — бот курсов валют ЦБ РФ.\n\n"
        "Что умею:\n"
        "• /start — главное меню\n"
        "• /rates — список курсов\n"
        "• /rate USD — курс одной валюты\n"
        "• 100 USD в RUB — конвертер\n\n"
        "Все данные — официальные курсы ЦБ."
    )

@bot.message_handler(commands=["rates"])
def rates(message):
    data = get_rates()
    if not data:
        bot.send_message(message.chat.id, "⚠️ Не удалось получить курсы.")
        return
    lines = ["📊 **Курсы ЦБ РФ:**\n"]
    for code, name in CURRENCIES.items():
        val = data["Valute"][code]
        course = val["Value"] / val["Nominal"]
        lines.append(f"{name} ({code}): {course:.2f} ₽")
    bot.send_message(message.chat.id, "\n".join(lines), parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(commands=["rate"])
def rate(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "Напиши так: /rate USD")
        return
    code = parts[1].upper()
    bot.send_message(message.chat.id, rate_text(code), parse_mode="Markdown")

# НОВЫЙ УМНЫЙ КОНВЕРТЕР
@bot.message_handler(func=lambda m: True)  # ловит ВСЕ сообщения
def converter(message):
    text = message.text
    # Ищем паттерн: число (с точкой или запятой) + пробел + 3 буквы (валюта) + что угодно + 3 буквы (валюта)
    # Пример: 100.5 USD в RUB, 100,5 USD RUB, 50 EUR to RUB
    pattern = r'([\d]+(?:[.,]\d+)?)\s+([A-Z]{3})\s+.*?([A-Z]{3})'
    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        amount_str, from_code, to_code = match.groups()
        from_code = from_code.upper()
        to_code = to_code.upper()

        # Заменяем запятую на точку для float
        amount = float(amount_str.replace(',', '.'))

        data = get_rates()
        if not data:
            bot.send_message(message.chat.id, "⚠️ Не удалось получить курсы. Попробуй позже.")
            return

        valutes = data["Valute"]

        def to_rub(code):
            if code == "RUB":
                return 1.0
            val = valutes.get(code)
            if not val:
                raise KeyError(f"Валюта {code} не найдена")
            return val["Value"] / val["Nominal"]

        try:
            result = amount * to_rub(from_code) / to_rub(to_code)
            bot.send_message(
                message.chat.id,
                f"💱 {amount:g} {from_code} = **{result:,.2f} {to_code}**\n"
                f"(по курсу ЦБ РФ)",
                parse_mode="Markdown"
            )
        except KeyError:
            bot.send_message(message.chat.id, f"⚠️ Валюта не найдена: проверь коды ({from_code}, {to_code})")
    else:
        # Если сообщение не похоже на конвертер, не отвечаем на него автоматически.
        # Но чтобы не спамить, мы просто ничего не делаем, если это не команда.
        pass

@bot.callback_query_handler(func=lambda c: c.data.startswith("rate:"))
def callback_rate(call):
    code = call.data.split(":")[1]
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, rate_text(code), parse_mode="Markdown")

if __name__ == "__main__":
    print("Бот запущен!")
    bot.infinity_polling(skip_pending=True)
