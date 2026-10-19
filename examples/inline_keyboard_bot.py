"""Inline keyboard + callback query handling with GramLite."""

import logging

from gramlite import Bot, InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

bot = Bot("YOUR-BOT-TOKEN")


@bot.message_handler(commands=["start"])
def welcome(message):
    markup = (
        InlineKeyboardMarkup(row_width=2)
        .add(
            InlineKeyboardButton("Buy 1 ticket", callback_data="buy:1"),
            InlineKeyboardButton("Buy 2 tickets", callback_data="buy:2"),
        )
        .row(InlineKeyboardButton("Visit our site", url="https://example.com"))
    )
    bot.send_message(message.chat.id, "Welcome! Pick an option:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("buy:"))
def on_buy(call):
    quantity = call.data.split(":")[1]
    bot.answer_callback_query(call.id, text=f"Added {quantity} ticket(s)!")
    bot.edit_message_text(
        f"Order confirmed: {quantity} ticket(s).",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
    )


@bot.message_handler(func=lambda message: True)
def fallback(message):
    bot.send_message(message.chat.id, "Use /start to see the menu.")


if __name__ == "__main__":
    bot.infinity_polling()
