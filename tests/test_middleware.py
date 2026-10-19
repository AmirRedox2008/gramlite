"""Tests for middleware chains (sync) and the exception-handler hook."""

from __future__ import annotations

from gramlite.bot import Bot
from gramlite.types import Update

from conftest import CALLBACK_UPDATE_JSON, TOKEN, UPDATE_JSON, RecordingClient


def _make_bot():
    return Bot(token=TOKEN, client=RecordingClient(None))


def _msg_update(text="hello"):
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": 42, "is_bot": False, "first_name": "Ada"},
            "chat": {"id": 42, "type": "private", "first_name": "Ada"},
            "date": 1760000000,
            "text": text,
        },
    }
    if text.startswith("/"):
        command = text.split(maxsplit=1)[0]
        payload["message"]["entities"] = [
            {"type": "bot_command", "offset": 0, "length": len(command)}
        ]
    return Update.de_json(payload)


def _callback_update():
    return Update.de_json(CALLBACK_UPDATE_JSON)


def test_middleware_runs_before_handler():
    bot = _make_bot()
    order = []

    @bot.register_middleware(update_types=["message"])
    def mw(message, next_):
        order.append("middleware")
        next_()

    @bot.message_handler(func=lambda m: True)
    def handler(message):
        order.append("handler")

    bot.process_new_updates([_msg_update()])
    assert order == ["middleware", "handler"]


def test_middleware_chain_order_is_registration_order():
    bot = _make_bot()
    order = []

    @bot.register_middleware()
    def first(message, next_):
        order.append("first")
        next_()

    @bot.register_middleware()
    def second(message, next_):
        order.append("second")
        next_()

    @bot.message_handler(func=lambda m: True)
    def handler(message):
        order.append("handler")

    bot.process_new_updates([_msg_update()])
    assert order == ["first", "second", "handler"]


def test_middleware_can_short_circuit():
    bot = _make_bot()
    order = []

    @bot.register_middleware(update_types=["message"])
    def gate(message, next_):
        order.append("gate")
        # no next_() → handler must never run

    @bot.message_handler(func=lambda m: True)
    def handler(message):
        order.append("handler")

    assert bot.process_new_updates([_msg_update()]) == 1
    assert order == ["gate"]


def test_middleware_scoped_to_other_update_type_never_runs():
    bot = _make_bot()
    order = []

    @bot.register_middleware(update_types=["callback_query"])
    def callback_only(payload, next_):
        order.append("callback_only")

    @bot.message_handler(func=lambda m: True)
    def handler(message):
        order.append("handler")

    bot.process_new_updates([_msg_update()])
    assert order == ["handler"]


def test_middleware_sees_every_payload_kind_when_unscoped():
    bot = _make_bot()
    seen = []

    @bot.register_middleware()
    def spy(payload, next_):
        seen.append(type(payload).__name__)
        next_()

    @bot.callback_query_handler(func=lambda c: True)
    def callback_handler(call):
        pass

    bot.process_new_updates([_callback_update()])
    assert seen == ["CallbackQuery"]


def test_exception_handler_receives_payload_and_exception():
    bot = _make_bot()
    caught = []

    @bot.exception_handler
    def on_error(payload, exception):
        caught.append((type(payload).__name__, str(exception)))

    @bot.message_handler(commands=["start"])
    def broken(message):
        raise RuntimeError("boom")

    with ExceptionCatcher():
        bot.process_new_updates([Update.de_json(UPDATE_JSON)])
    assert caught == [("Message", "boom")]


def test_handler_exception_is_logged_without_exception_handler(caplog):
    import logging

    bot = _make_bot()

    @bot.message_handler(commands=["start"])
    def broken(message):
        raise RuntimeError("kaboom")

    with caplog.at_level(logging.ERROR, logger="gramlite.handlers"):
        bot.process_new_updates([Update.de_json(UPDATE_JSON)])
    assert any("raised inside message" in r.getMessage() for r in caplog.records)


def test_custom_filter_class():
    from gramlite.handlers import BaseFilter

    class AdminOnly(BaseFilter):
        name = "AdminOnly"

        def check(self, message):
            return message.from_user.id == 42

    bot = _make_bot()
    hits = []

    @bot.message_handler(commands=["panel"], custom_filter=AdminOnly())
    def panel(message):
        hits.append(message.message_id)

    bot.process_new_updates([_msg_update("/panel")])   # admin → runs
    assert len(hits) == 1

    stranger = _msg_update("/panel")
    stranger.message.from_user.id = 7
    bot.process_new_updates([stranger])                # non-admin → skipped
    assert len(hits) == 1


def test_pass_args_passes_command_arguments():
    bot = _make_bot()
    received = []

    @bot.message_handler(commands=["ban"], pass_args=True)
    def ban(message, *args):
        received.append(args)

    bot.process_new_updates([_msg_update("/ban 42 spam")])
    assert received == [("42", "spam")]


def test_command_mentioned_to_another_bot_is_ignored():
    bot = _make_bot()
    bot.router.bot_username = "mybot"
    hits = []

    @bot.message_handler(commands=["start"])
    def start(message):
        hits.append(message)

    bot.process_new_updates([_msg_update("/start@otherbot")])
    assert hits == []
    bot.process_new_updates([_msg_update("/start@mybot")])
    assert hits == [hits[-1]] and len(hits) == 1


class ExceptionCatcher:
    """Keeps pytest from failing on exceptions swallowed by the dispatcher."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
