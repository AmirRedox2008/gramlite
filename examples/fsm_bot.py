"""FSM bot — a multi-step registration form (Persian UI).

Run:  python examples/fsm_bot.py
Docs: gramlite.fsm — states survive restarts thanks to JSONFileStorage.
"""

import logging

from gramlite import Bot
from gramlite.fsm import JSONFileStorage, State, StateGroup
from gramlite.utils import escape_html

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bot = Bot("YOUR-BOT-TOKEN", storage=JSONFileStorage("bot_states.json"))


class Form(StateGroup):
    """Each attribute becomes a state: 'Form:name', 'Form:age', ..."""

    name = State()
    age = State()
    city = State()


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "سلام! برای ثبت‌نام /form را بزنید. /cancel برای انصراف.")


@bot.message_handler(commands=["cancel"])
def cancel(message):
    bot.reset_state(message.from_user.id, message.chat.id)
    bot.reply_to(message, "انصراف داده شد.")


@bot.message_handler(commands=["form"])
def begin(message):
    bot.set_state(message.from_user.id, Form.name, message.chat.id)
    bot.reply_to(message, "اسمت چیه؟")


@bot.message_handler(state=Form.name)
def ask_age(message):
    bot.update_state_data(message.from_user.id, name=message.text, chat_id=message.chat.id)
    bot.set_state(message.from_user.id, Form.age, message.chat.id)
    bot.reply_to(message, "خوشوقتم! چند سالته؟")


@bot.message_handler(state=Form.age)
def ask_city(message):
    if not message.text or not message.text.isdigit():
        bot.reply_to(message, "لطفاً فقط عدد بفرست 🙂")
        return
    bot.update_state_data(message.from_user.id, age=int(message.text), chat_id=message.chat.id)
    bot.set_state(message.from_user.id, Form.city, message.chat.id)
    bot.reply_to(message, "کدوم شهری؟")


@bot.message_handler(state=Form.city)
def finish(message):
    data = bot.update_state_data(message.from_user.id, city=message.text, chat_id=message.chat.id)
    bot.reset_state(message.from_user.id, message.chat.id)
    bot.reply_to(
        message,
        "✅ ثبت‌نام کامل شد:\n"
        f"نام: <b>{escape_html(data['name'])}</b>\n"
        f"سن: {data['age']}\n"
        f"شهر: <b>{escape_html(data['city'])}</b>",
    )


@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"))
def fallback(message):
    """Any non-command text while NOT in a state lands here."""
    bot.reply_to(message, "برای شروع /form را بزنید.")


@bot.exception_handler
def on_error(payload, exception):
    logging.exception("Error processing %s", payload, exc_info=exception)


if __name__ == "__main__":
    bot.infinity_polling()
