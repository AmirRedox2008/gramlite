"""Tests for the FSM: state groups, storages, the state filter and data."""

from __future__ import annotations

import json

import pytest

from gramlite.bot import Bot
from gramlite.fsm import JSONFileStorage, MemoryStorage, State, StateGroup
from gramlite.types import Update

from conftest import TOKEN, UPDATE_JSON, RecordingClient


class Form(StateGroup):
    name = State()
    age = State()


def _make_bot(**kwargs):
    return Bot(token=TOKEN, client=RecordingClient(None), **kwargs)


def _message_update(text: str, user_id: int = 42, chat_id: int = 42) -> Update:
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "is_bot": False, "first_name": "Ada"},
            "chat": {"id": chat_id, "type": "private", "first_name": "Ada"},
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


# ---------------------------------------------------------------------------
# StateGroup mechanics
# ---------------------------------------------------------------------------
def test_state_group_fills_names():
    assert Form.name.full_name == "Form:name"
    assert Form.age.full_name == "Form:age"


def test_state_full_name_is_canonical_string():
    assert Form.name.full_name.startswith("Form:")
    assert isinstance(Form.name, State)


# ---------------------------------------------------------------------------
# Bot FSM API
# ---------------------------------------------------------------------------
def test_set_get_reset_state_roundtrip():
    bot = _make_bot()
    assert bot.get_state(42) is None
    bot.set_state(42, Form.name)
    assert bot.get_state(42) == "Form:name"
    bot.reset_state(42)
    assert bot.get_state(42) is None


def test_state_is_scoped_per_chat():
    bot = _make_bot()
    bot.set_state(42, Form.name, chat_id=100)
    assert bot.get_state(42, chat_id=100) == "Form:name"
    assert bot.get_state(42, chat_id=200) is None


def test_state_data_roundtrip():
    bot = _make_bot()
    bot.update_state_data(42, name="Ada", chat_id=1)
    assert bot.get_state_data(42, 1) == {"name": "Ada"}
    bot.update_state_data(42, age=36, chat_id=1)
    assert bot.get_state_data(42, 1) == {"name": "Ada", "age": 36}
    bot.clear_state_data(42, 1)
    assert bot.get_state_data(42, 1) == {}


# ---------------------------------------------------------------------------
# The state= filter
# ---------------------------------------------------------------------------
def test_state_filter_routes_by_state():
    bot = _make_bot()
    hits = []

    @bot.message_handler(state=Form.name)
    def name_step(message):
        hits.append("name")

    @bot.message_handler(state=Form.age)
    def age_step(message):
        hits.append("age")

    bot.set_state(42, Form.age, chat_id=42)
    bot.process_new_updates([_message_update("36")])
    assert hits == ["age"]


def test_state_star_matches_any_state():
    bot = _make_bot()
    hits = []

    @bot.message_handler(state="*")
    def any_step(message):
        hits.append("any")

    bot.set_state(42, Form.name, chat_id=42)
    bot.process_new_updates([_message_update("hi")])
    assert hits == ["any"]


def test_handlers_without_state_run_always():
    bot = _make_bot()
    hits = []

    @bot.message_handler(commands=["start"])
    def start(message):
        hits.append("start")

    bot.set_state(42, Form.name, chat_id=42)
    bot.process_new_updates([_message_update("/start")])
    assert hits == ["start"]


def test_state_filter_combines_with_other_filters():
    bot = _make_bot()
    hits = []

    @bot.message_handler(commands=["next"], state=Form.name)
    def combined(message):
        hits.append("combined")

    bot.set_state(42, Form.age, chat_id=42)  # wrong state
    bot.process_new_updates([_message_update("/next")])
    assert hits == []
    bot.set_state(42, Form.name, chat_id=42)  # right state
    bot.process_new_updates([_message_update("/next")])
    assert hits == ["combined"]


# ---------------------------------------------------------------------------
# JSONFileStorage
# ---------------------------------------------------------------------------
def test_json_storage_persists_across_instances(tmp_path):
    path = tmp_path / "states.json"
    storage = JSONFileStorage(path)
    storage.set_state(42, 7, "Form:name")
    storage.update_data(42, 7, answer="ok")

    reloaded = JSONFileStorage(path)
    assert reloaded.get_state(42, 7) == "Form:name"
    assert reloaded.get_data(42, 7) == {"answer": "ok"}


def test_json_storage_handles_corrupt_file(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    storage = JSONFileStorage(path)  # must not raise
    assert storage.get_state(1) is None


def test_json_storage_is_the_persisted_document(tmp_path):
    path = tmp_path / "states.json"
    JSONFileStorage(path).set_state(1, 1, "Form:age")
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh) == {"1:1": {"state": "Form:age"}}


# ---------------------------------------------------------------------------
# Concurrency guard
# ---------------------------------------------------------------------------
def test_memory_storage_clear_removes_everything():
    storage = MemoryStorage()
    storage.set_state(1, 1, "Form:name")
    storage.set_data(1, 1, {"a": 1})
    storage.clear(1, 1)
    assert storage.get_state(1, 1) is None
    assert storage.get_data(1, 1) == {}


def test_redis_storage_import_error_is_helpful():
    try:
        import redis  # noqa: F401
        pytest.skip("redis installed — the ImportError path cannot be tested")
    except ImportError:
        pass
    from gramlite.fsm import RedisStorage
    with pytest.raises(ImportError, match="gramlite\\[redis\\]"):
        RedisStorage()
