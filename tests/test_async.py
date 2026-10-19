"""Tests for the async stack (aiohttp required, but all calls are faked)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("aiohttp")

from gramlite.async_bot import AsyncBot  # noqa: E402
from gramlite.types import Message, Update  # noqa: E402

from conftest import (  # noqa: E402
    CALLBACK_UPDATE_JSON, COMMAND_MESSAGE_JSON, TOKEN, UPDATE_JSON,
)


class FakeAsyncClient:
    """Records calls and returns canned results (mirrors RecordingClient)."""

    def __init__(self, results, token=TOKEN):
        self.token = token
        self.results = list(results)
        self.calls = []

    async def request(self, method_name, params=None, files=None, timeout=None):
        self.calls.append({"method": method_name, "params": params, "files": files})
        if len(self.results) == 1:
            return self.results[0]
        return self.results.pop(0)

    def file_download_url(self, file_path):
        return f"https://api.telegram.org/file/bot{self.token}/{file_path}"

    async def get_bytes(self, url, timeout=None):
        self.calls.append({"method": "GET", "url": url})
        return b"file-bytes-here"

    async def close(self):
        pass


def _run(coro):
    return asyncio.run(coro)


def test_async_send_message_maps_params_and_parses():
    client = FakeAsyncClient([COMMAND_MESSAGE_JSON])

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)
        return await bot.send_message(42, "hello")

    message = _run(main())
    assert isinstance(message, Message)
    assert client.calls[0]["method"] == "sendMessage"
    assert client.calls[0]["params"]["chat_id"] == 42


def test_async_reply_to():
    client = FakeAsyncClient([COMMAND_MESSAGE_JSON])

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)
        message = Message.de_json(COMMAND_MESSAGE_JSON)
        return await bot.reply_to(message, "hi there")

    _run(main())
    params = client.calls[0]["params"]
    assert params["reply_to_message_id"] == 7


def test_async_get_updates_and_type_parsing():
    client = FakeAsyncClient([[UPDATE_JSON]])

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)
        return await bot.get_updates(offset=None, timeout=3)

    updates = _run(main())
    assert isinstance(updates[0], Update)
    assert updates[0].update_id == 100


def test_async_callback_routing():
    client = FakeAsyncClient([None])
    received = []

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)

        @bot.callback_query_handler(func=lambda c: True)
        def handler(call):
            received.append(call)

        return await bot.process_new_updates([CALLBACK_UPDATE_JSON])

    _run(main())
    assert received[0].data == "buy:3"


def test_async_handlers_are_genuinely_awaited():
    """Regression for the v1 bug: ``async def`` handlers were never awaited."""
    client = FakeAsyncClient([None])
    received = []

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)

        @bot.message_handler(func=lambda m: True)
        async def handler(message):  # must be awaited by the dispatcher
            received.append(message.text)

        await bot.process_new_updates([UPDATE_JSON])

    _run(main())
    assert received == ["/start@mybot hello"]


def test_async_middleware_short_circuit():
    client = FakeAsyncClient([None])
    received = []

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)

        @bot.register_middleware(update_types=["message"])
        async def gate(message, next_):
            return "blocked"  # never calls next_() → handler must not run

        @bot.message_handler(func=lambda m: True)
        async def handler(message):
            received.append(message)

        await bot.process_new_updates([UPDATE_JSON])

    _run(main())
    assert received == []


def test_async_polling_offset_advances():
    client = FakeAsyncClient([
        [UPDATE_JSON],
        [{"update_id": 101, "message": COMMAND_MESSAGE_JSON}],
        [],
    ])
    received = []

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)

        @bot.message_handler(func=lambda m: True)
        def handler(message):
            received.append(message)
            if len(received) >= 2:
                stop_event.set()

        stop_event = asyncio.Event()
        # handler closes over stop_event — patch via nonlocal-free trick:
        return await bot.polling(long_polling_timeout=0, stop_event=stop_event)

    _run(main())
    assert len(received) == 2
    offsets = [call["params"]["offset"] for call in client.calls]
    assert offsets[0] is None
    assert offsets[1] == 101


def test_async_media_string_file_id():
    client = FakeAsyncClient([COMMAND_MESSAGE_JSON])

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)
        return await bot.send_document(1, "DOC-1")

    message = _run(main())
    assert isinstance(message, Message)
    assert client.calls[0]["method"] == "sendDocument"
    assert client.calls[0]["files"] is None


def test_async_context_manager_closes_session():
    client = FakeAsyncClient([{"id": 1, "is_bot": True, "first_name": "B"}])

    async def main():
        closed = {"flag": False}

        class TrackingClient(FakeAsyncClient):
            async def close(self):
                closed["flag"] = True

        async with AsyncBot(token=TOKEN, client=TrackingClient([None])) as bot:
            await bot.get_me()
        return closed["flag"]

    assert _run(main()) is True


def test_async_new_api_methods_map():
    client = FakeAsyncClient([True, [{"command": "start", "description": "s"}]])

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)
        await bot.set_my_commands([("start", "s")])
        commands = await bot.get_my_commands()
        return commands

    commands = _run(main())
    assert commands[0].command == "start"
    assert client.calls[0]["method"] == "setMyCommands"


def test_async_fsm_state_filter():
    from gramlite.fsm import State, StateGroup

    class Quiz(StateGroup):
        waiting = State()

    client = FakeAsyncClient([None])
    received = []

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)

        @bot.message_handler(state=Quiz.waiting)
        async def step(message):
            received.append(message.text)

        bot.set_state(42, Quiz.waiting, chat_id=UPDATE_JSON["message"]["chat"]["id"])
        await bot.process_new_updates([UPDATE_JSON])

    _run(main())
    assert received == ["/start@mybot hello"]


def test_async_download_file():
    client = FakeAsyncClient([{"file_id": "x", "file_unique_id": "y", "file_path": "docs/a.txt"}])

    async def main():
        bot = AsyncBot(token=TOKEN, client=client)
        return await bot.download_file("docs/a.txt")

    assert _run(main()) == b"file-bytes-here"
