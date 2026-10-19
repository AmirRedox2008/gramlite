"""Tests for the handler system: filters, ordering and dispatch."""

from __future__ import annotations

from gramlite.handlers import HandlerRegistry
from gramlite.types import Update

from conftest import UPDATE_JSON


def _registry_with_capture():
    registry = HandlerRegistry()
    received = []
    return registry, received


# ---------------------------------------------------------------------------
# Message filters
# ---------------------------------------------------------------------------
def test_command_filter_matches_and_passes_message(sample_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), commands=["start"])

    assert registry.process_update(sample_update) is True
    assert len(received) == 1
    assert received[0].message_id == 7


def test_command_filter_rejects_other_commands(sample_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), commands=["help"])
    assert registry.process_update(sample_update) is False
    assert received == []


def test_content_types_filter(sample_update, photo_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), content_types=["photo"])

    assert registry.process_update(sample_update) is False   # text message
    assert registry.process_update(photo_update) is True     # photo message
    assert len(received) == 1


def test_content_types_all_accepts_everything(sample_update, photo_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), content_types=["all"])
    assert registry.process_update(sample_update) is True
    assert registry.process_update(photo_update) is True
    assert len(received) == 2


def test_regexp_filter(sample_update, photo_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), regexp=r"hello")

    assert registry.process_update(sample_update) is True
    assert registry.process_update(photo_update) is False  # no text at all


def test_func_filter(sample_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), func=lambda m: "hello" in m.text)
    assert registry.process_update(sample_update) is True


def test_chat_types_filter(sample_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append(m), chat_types=["supergroup"])
    assert registry.process_update(sample_update) is True

    registry_private, received_private = _registry_with_capture()
    registry_private.add("message", lambda m: received_private.append(m), chat_types=["private"])
    assert registry_private.process_update(sample_update) is False


def test_first_registered_handler_wins(sample_update):
    registry, received = _registry_with_capture()
    registry.add("message", lambda m: received.append("first"), commands=["start"])
    registry.add("message", lambda m: received.append("second"), func=lambda m: True)

    assert registry.process_update(sample_update) is True
    assert received == ["first"]


def test_stacked_decorator_equivalent_registration(sample_update):
    registry, received = _registry_with_capture()
    # Simulate stacked decorators: same function registered twice.
    def handler(m):
        received.append(m)

    registry.add("message", handler, commands=["hello"])
    registry.add("message", handler, func=lambda m: True)

    assert registry.process_update(sample_update) is True
    assert len(received) == 1  # matched via the second registration


# ---------------------------------------------------------------------------
# Callback queries
# ---------------------------------------------------------------------------
def test_callback_query_routing(callback_update):
    registry, received = _registry_with_capture()
    registry.add("callback_query", lambda c: received.append(c), func=lambda c: "buy" in c.data)
    assert registry.process_update(callback_update) is True
    assert received[0].data == "buy:3"


def test_callback_query_filter_mismatch(callback_update):
    registry, received = _registry_with_capture()
    registry.add("callback_query", lambda c: received.append(c), func=lambda c: c.data.startswith("sell"))
    assert registry.process_update(callback_update) is False
    assert received == []


# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------
def test_handler_exception_is_swallowed_and_logged(sample_update, caplog):
    registry = HandlerRegistry()

    def broken(message):
        raise RuntimeError("boom")

    registry.add("message", broken, commands=["start"])

    import logging
    with caplog.at_level(logging.ERROR, logger="gramlite.handlers"):
        assert registry.process_update(sample_update) is True
    errors = [record for record in caplog.records if record.levelname == "ERROR"]
    assert any("raised inside message" in record.getMessage() for record in errors)


def test_update_with_no_payload_returns_false():
    registry, received = _registry_with_capture()
    empty = Update.de_json({"update_id": 999})
    assert registry.process_update(empty) is False


def test_process_new_updates_accepts_raw_dicts(sample_update):
    from gramlite.bot import Bot
    from conftest import RecordingClient, TOKEN

    bot = Bot(token=TOKEN, client=RecordingClient(None))
    received = []
    bot.router.add("message", lambda m: received.append(m), commands=["start"])
    assert bot.process_new_updates([dict(UPDATE_JSON)]) == 1
    assert len(received) == 1
