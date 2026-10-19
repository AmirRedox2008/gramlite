"""Webhook bot — Flask + GramLite.

Run (local dev with a tunnel like ngrok/cloudflared):

    python examples/webhook_flask.py
    # then: bot.set_webhook("https://<your-domain>/webhook") once
"""

import logging

from flask import Flask, request

from gramlite import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
bot = Bot("YOUR-BOT-TOKEN", parse_mode="HTML")


@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "این بات روی <b>webhook</b> کار می‌کند — بدون polling!")


@bot.message_handler(commands=["ping"])
def ping(message):
    bot.reply_to(message, "pong")


@bot.message_handler(func=lambda m: True, content_types=["all"])
def fallback(message):
    bot.reply_to(message, f"got: {message.content_type}")


@app.route("/webhook", methods=["POST"])
def webhook():
    """One POST = one Telegram update. The router does the rest."""
    bot.process_webhook_update(request.get_json(force=True))
    return "ok", 200


@app.route("/healthz")
def healthz():
    return {"ok": True, "bot": bot.username}


if __name__ == "__main__":
    # register the webhook once, then serve:
    bot.set_webhook("https://YOUR-DOMAIN/webhook", secret_token="optional-secret")
    app.run(host="0.0.0.0", port=8443)
