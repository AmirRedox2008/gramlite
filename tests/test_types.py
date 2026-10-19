"""Tests for type parsing and keyboard serialisation."""

from __future__ import annotations

import json

import pytest

from gramlite.types import (
    CallbackQuery, Chat, ChatMemberUpdated, File, ForceReply,
    InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, User,
)

from conftest import CALLBACK_UPDATE_JSON, COMMAND_MESSAGE_JSON, UPDATE_JSON


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def test_message_parses_from_as_from_user(sample_message):
    assert sample_message.from_user.username == "ada"
    assert sample_message.from_user.full_name == "Ada Lovelace"


def test_message_chat_is_parsed(sample_message):
    assert isinstance(sample_message.chat, Chat)
    assert sample_message.chat.type == "supergroup"
    assert sample_message.chat.title == "Test Group"


def test_content_type_text(sample_message):
    assert sample_message.content_type == "text"


def test_content_type_photo(photo_update):
    message = photo_update.message
    assert message.content_type == "photo"
    assert len(message.photo) == 2
    assert message.photo[0].file_id == "small_fid"


def test_missing_fields_return_none_instead_of_raising(sample_message):
    assert sample_message.audio is None
    assert sample_message.location is None
    assert sample_message.not_a_real_field is None


def test_entities_are_parsed(sample_message):
    assert sample_message.entities[0].type == "bot_command"
    assert sample_message.is_command is True
    assert sample_message.extract_command() == "start"


def test_extract_command_handles_bot_suffix_and_case():
    message = Message.de_json(COMMAND_MESSAGE_JSON)
    assert message.extract_command() == "start"


def test_plain_message_is_not_a_command(photo_update):
    assert photo_update.message.is_command is False


def test_update_effective_message(sample_update):
    assert sample_update.effective_message is sample_update.message


def test_update_effective_message_for_callback(callback_update):
    assert callback_update.effective_message is callback_update.callback_query.message


def test_callback_query_parses_from_user(callback_update):
    query = callback_update.callback_query
    assert isinstance(query, CallbackQuery)
    assert query.from_user.username == "ada"
    assert query.data == "buy:3"


def test_de_json_none_is_none():
    assert Message.de_json(None) is None
    assert Update.de_json(None) is None
    assert User.de_json(None) is None


def test_unknown_fields_are_parsed_into_typed_objects():
    update = Update.de_json({**UPDATE_JSON, "my_chat_member": {"status": "kicked"}})
    assert isinstance(update.my_chat_member, ChatMemberUpdated)
    assert update.my_chat_member.status == "kicked"


def test_genuinely_unknown_fields_are_preserved():
    update = Update.de_json({**UPDATE_JSON, "future_field": {"a": 1}})
    assert update.future_field == {"a": 1}


def test_user_mention_html():
    user = User.de_json({"id": 42, "is_bot": False, "first_name": "Ada"})
    assert user.mention() == '<a href="tg://user?id=42">Ada</a>'


def test_file_type():
    f = File.de_json({"file_id": "x", "file_unique_id": "y", "file_path": "a/b.txt"})
    assert f.file_path == "a/b.txt"


# ---------------------------------------------------------------------------
# Keyboard serialisation
# ---------------------------------------------------------------------------
def test_reply_keyboard_add_wraps_rows():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("a"), KeyboardButton("b"), KeyboardButton("c"))
    data = markup.to_dict()
    assert data["resize_keyboard"] is True
    assert data["keyboard"] == [[{"text": "a"}, {"text": "b"}], [{"text": "c"}]]


def test_reply_keyboard_row_appends_single_row():
    markup = ReplyKeyboardMarkup()
    markup.row(KeyboardButton("yes"), KeyboardButton("no"))
    assert markup.to_dict()["keyboard"] == [[{"text": "yes"}, {"text": "no"}]]


def test_inline_keyboard_serialisation():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Buy", callback_data="buy:1"),
        InlineKeyboardButton("Site", url="https://example.com"),
    )
    data = markup.to_dict()
    assert data == {"inline_keyboard": [[
        {"text": "Buy", "callback_data": "buy:1"},
        {"text": "Site", "url": "https://example.com"},
    ]]}
    # must be directly JSON-serialisable (what prepare_params relies on)
    assert json.loads(json.dumps(data)) == data


def test_inline_button_requires_callback_data_or_url():
    with pytest.raises(ValueError):
        InlineKeyboardButton("broken")


def test_reply_keyboard_remove_serialisation():
    assert ReplyKeyboardRemove().to_dict() == {"remove_keyboard": True}
    assert ReplyKeyboardRemove(selective=True).to_dict() == {"remove_keyboard": True, "selective": True}


def test_force_reply_serialisation():
    assert ForceReply().to_dict() == {"force_reply": True}
    forced = ForceReply(input_field_placeholder="type now")
    assert forced.to_dict()["force_reply"] is True
    assert forced.to_dict()["input_field_placeholder"] == "type now"
