"""Middleware + admin-gate bot — chain-of-responsibility in action.

Run:  python examples/middleware_bot.py
"""

import logging
import time

from gramlite import Bot
from gramlite.handlers import BaseFilter
from gramlite.types import Message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bot = Bot("YOUR-BOT-TOKEN", parse_mode="HTML")

ADMINS = {123456789}          # your Telegram user id
BANNED = set()
_last_seen: dict[int, float] = {}


class AdminFilter(BaseFilter):
    """Reusable custom filter: only admins pass."""

    name = "AdminFilter"

    def check(self, message: Message) -> bool:
        return bool(message.from_user) and message.from_user.id in ADMINS


# --- middleware: logging gate -------------------------------------------------
@bot.register_middleware(update_types=["message"])
def logger_mw(message: Message, next_):
    logging.info("message from %s in %s", message.from_user.id, message.chat.id)
    next_()


# --- middleware: ban gate (short-circuits banned users) -----------------------
@bot.register_middleware(update_types=["message"])
def ban_gate(message: Message, next_):
    if message.from_user and message.from_user.id in BANNED:
        return                    # no next_() → handlers never run
    next_()


# --- middleware: naive 1 msg / 3 s flood control ------------------------------
@bot.register_middleware(update_types=["message"])
def flood_gate(message: Message, next_):
    uid = message.from_user.id if message.from_user else 0
    now = time.monotonic()
    if now - _last_seen.get(uid, 0) < 3:
        bot.reply_to(message, "آروم‌تر! ⏳")
        return
    _last_seen[uid] = now
    next_()


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "سلام! من با <b>middleware</b> محافظت می‌شم.")


@bot.message_handler(commands=["admin"], custom_filter=AdminFilter())
def admin_panel(message):
    bot.reply_to(message, f"پنل مدیریت — خوش آمدی {message.from_user.full_name}!")


@bot.message_handler(commands=["ban"], pass_args=True, custom_filter=AdminFilter())
def ban(message, *args):
    BANNED.add(int(args[0]))
    bot.reply_to(message, f"کاربر <code>{args[0]}</code> بن شد.")


@bot.message_handler(func=lambda m: True, content_types=["text"])
def echo(message):
    bot.reply_to(message, escape(message.text))


def escape(text: str) -> str:
    from gramlite import escape_html
    return escape_html(text or "")


@bot.exception_handler
def on_error(payload, exception):
    logging.error("dispatch error: %s", exception)


if __name__ == "__main__":
    bot.infinity_polling()
