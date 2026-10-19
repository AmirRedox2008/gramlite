"""Tests for the Bot facade: method/params mapping and response parsing."""

from __future__ import annotations

import io
import json

from gramlite.bot import Bot
from gramlite.types import (
    File, InlineKeyboardButton, InlineKeyboardMarkup, Message, User,
)

from conftest import CALLBACK_UPDATE_JSON, COMMAND_MESSAGE_JSON, TOKEN, RecordingClient, UPDATE_JSON


def test_send_message_maps_params_and_parses(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    message = bot.send_message(42, "hello", parse_mode="HTML")
    assert isinstance(message, Message)
    assert message.message_id == 7
    call = recording_client.calls[0]
    assert call["method"] == "sendMessage"
    assert call["params"]["chat_id"] == 42
    assert call["params"]["text"] == "hello"
    assert call["params"]["parse_mode"] == "HTML"


def test_reply_to_uses_chat_id_and_reply_id(bot, recording_client):
    message = Message.de_json(COMMAND_MESSAGE_JSON)
    bot.reply_to(message, "hi")
    params = recording_client.calls[0]["params"]
    assert params["chat_id"] == message.chat.id
    assert params["reply_to_message_id"] == message.message_id


def test_get_me_returns_user(bot):
    bot.client.result = {"id": 1, "is_bot": True, "first_name": "GramLite Bot"}
    me = bot.get_me()
    assert isinstance(me, User)
    assert me.is_bot is True


def test_get_updates_returns_updates(bot, recording_client):
    bot.client.result = [UPDATE_JSON]
    updates = bot.get_updates(offset=None, timeout=5, allowed_updates=["message"])
    assert updates[0].update_id == 100
    params = recording_client.calls[0]["params"]
    assert params["timeout"] == 5
    assert json.loads(params["allowed_updates"]) == ["message"]


def test_edit_message_text_returns_message(bot):
    bot.client.result = COMMAND_MESSAGE_JSON
    assert isinstance(bot.edit_message_text("new", chat_id=1, message_id=7), Message)


def test_edit_message_text_inline_returns_bool(bot):
    bot.client.result = True
    assert bot.edit_message_text("new", inline_message_id="abc") is True


def test_delete_and_forward_return_types(bot, recording_client):
    bot.client.result = True
    assert bot.delete_message(1, 7) is True
    bot.client.result = {"message_id": 99}
    forwarded = bot.forward_message(2, 1, 7)
    assert forwarded.message_id == 99
    assert recording_client.calls[-1]["method"] == "forwardMessage"


def test_send_media_with_string_file_id(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    message = bot.send_photo(42, "FID-123")
    assert isinstance(message, Message)
    assert recording_client.calls[0]["files"] is None
    assert recording_client.calls[0]["params"]["photo"] == "FID-123"


def test_send_media_with_file_like(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    payload = io.BytesIO(b"fake-png-bytes")
    bot.send_photo(42, payload, caption="a photo")
    files = recording_client.calls[0]["files"]
    assert files is not None
    name, content = files["photo"]
    assert name == "upload"
    assert content == b"fake-png-bytes"
    assert "photo" not in recording_client.calls[0]["params"]


def test_send_media_with_path(bot, recording_client, tmp_path):
    bot.client.result = COMMAND_MESSAGE_JSON
    photo = tmp_path / "pic.png"
    photo.write_bytes(b"png")
    bot.send_photo(42, photo)
    name, content = recording_client.calls[0]["files"]["photo"]
    assert name == "pic.png"
    assert content == b"png"


def test_send_media_all_kinds_map_to_methods(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    bot.send_document(1, "d")
    bot.send_video(1, "v")
    bot.send_audio(1, "a")
    bot.send_voice(1, "vo")
    bot.send_sticker(1, "s")
    methods = [call["method"] for call in recording_client.calls]
    assert methods == ["sendDocument", "sendVideo", "sendAudio", "sendVoice", "sendSticker"]


def test_reply_markup_is_passed_for_serialisation(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    markup = InlineKeyboardMarkup().row(InlineKeyboardButton("hi", callback_data="hi"))
    bot.send_message(1, "choose", reply_markup=markup)
    assert recording_client.calls[0]["params"]["reply_markup"] is markup


def test_answer_callback_query(bot, recording_client):
    bot.client.result = True
    assert bot.answer_callback_query("cbq-1", text="Done!") is True
    params = recording_client.calls[0]["params"]
    assert params["callback_query_id"] == "cbq-1"


def test_get_file_and_download_url(bot, recording_client):
    bot.client.result = {"file_id": "x", "file_unique_id": "y", "file_path": "docs/a.txt"}
    file = bot.get_file("x")
    assert isinstance(file, File)
    assert bot.download_file_url(file).endswith(f"/file/bot{TOKEN}/docs/a.txt")


def test_token_property(bot):
    assert bot.token == TOKEN


def test_decorators_register_and_route(recording_client):
    bot = Bot(token=TOKEN, client=recording_client)
    received = []

    @bot.message_handler(commands=["start"])
    def start_handler(message):
        received.append(message)

    @bot.callback_query_handler(func=lambda c: True)
    def callback_handler(call):
        received.append(call)

    bot.process_new_updates([UPDATE_JSON, CALLBACK_UPDATE_JSON])
    assert len(received) == 2
    assert received[0].text == "/start@mybot hello"
    assert received[1].data == "buy:3"


# ---------------------------------------------------------------------------
# v2 — new API methods
# ---------------------------------------------------------------------------
def test_send_poll_maps_params(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    bot.send_poll(42, "Coffee?", ["yes", "no"], is_anonymous=False)
    call = recording_client.calls[0]
    assert call["method"] == "sendPoll"
    assert call["params"]["options"] == ["yes", "no"]
    assert call["params"]["is_anonymous"] is False


def test_stop_poll_returns_poll(bot):
    bot.client.result = {"id": "p1", "question": "Q", "options": [{"text": "a", "voter_count": 1}]}
    poll = bot.stop_poll(1, 7)
    assert type(poll).__name__ == "Poll"
    assert poll.options[0].text == "a"


def test_send_dice_and_venue_and_contact_map_methods(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    bot.send_dice(1, emoji="🎯")
    bot.send_venue(1, 35.7, 51.4, "Cafe", "Tehran")
    bot.send_contact(1, "+98912", "Ada")
    methods = [c["method"] for c in recording_client.calls]
    assert methods == ["sendDice", "sendVenue", "sendContact"]


def test_send_animation_and_video_note_field_names(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    bot.send_animation(1, "GIF-1")
    bot.send_video_note(1, "VN-1")
    calls = recording_client.calls
    assert calls[0]["method"] == "sendAnimation" and calls[0]["params"]["animation"] == "GIF-1"
    assert calls[1]["method"] == "sendVideoNote" and calls[1]["params"]["video_note"] == "VN-1"


def test_send_media_group_serialises_media(bot, recording_client):
    from gramlite.types import InputMediaPhoto, InputMediaVideo
    bot.client.result = [COMMAND_MESSAGE_JSON, COMMAND_MESSAGE_JSON]
    messages = bot.send_media_group(1, [InputMediaPhoto("P1"), InputMediaVideo("V1")])
    assert len(messages) == 2
    call = recording_client.calls[0]
    assert call["method"] == "sendMediaGroup"
    assert call["params"]["media"][0] == {"type": "photo", "media": "P1"}


def test_edit_message_caption_and_markup(bot, recording_client):
    bot.client.result = True
    assert bot.edit_message_caption(chat_id=1, message_id=7, caption="new") is True
    assert recording_client.calls[0]["method"] == "editMessageCaption"
    assert bot.edit_message_reply_markup(chat_id=1, message_id=7) is True


def test_pin_and_unpin(bot, recording_client):
    bot.client.result = True
    bot.pin_chat_message(1, 7)
    bot.unpin_chat_message(1, 7)
    assert [c["method"] for c in recording_client.calls] == ["pinChatMessage", "unpinChatMessage"]


def test_chat_admin_surface(bot, recording_client):
    from gramlite.types import ChatPermissions
    bot.client.result = 17
    assert bot.get_chat_member_count(-100) == 17
    bot.client.result = {"status": "member", "user": {"id": 1, "is_bot": False, "first_name": "A"}}
    assert bot.get_chat_member(-100, 1).status == "member"
    bot.client.result = True
    bot.set_chat_title(-100, "New")
    bot.set_chat_permissions(-100, ChatPermissions(can_send_messages=False))
    bot.restrict_chat_member(-100, 5, ChatPermissions(can_send_messages=False))
    bot.promote_chat_member(-100, 5, can_delete_messages=True)
    bot.ban_chat_member(-100, 5, revoke_messages=True)
    methods = [c["method"] for c in recording_client.calls]
    assert methods == [
        "getChatMemberCount", "getChatMember", "setChatTitle", "setChatPermissions",
        "restrictChatMember", "promoteChatMember", "banChatMember",
    ]


def test_invite_links_and_join_requests(bot, recording_client):
    bot.client.result = "https://t.me/+abc"
    assert bot.export_chat_invite_link(-100).endswith("+abc")
    bot.client.result = {"invite_link": "https://t.me/+x", "creator": {"id": 1, "is_bot": False, "first_name": "A"}}
    link = bot.create_chat_invite_link(-100, name="promo", member_limit=10)
    assert type(link).__name__ == "ChatInviteLink"
    bot.client.result = True
    bot.approve_chat_join_request(-100, 5)
    assert recording_client.calls[-1]["method"] == "approveChatJoinRequest"


def test_bot_commands_surface(bot, recording_client):
    bot.client.result = True
    bot.set_my_commands([("start", "Start the bot"), ("help", "Get help")])
    params = recording_client.calls[0]["params"]
    assert params["commands"] == [
        {"command": "start", "description": "Start the bot"},
        {"command": "help", "description": "Get help"},
    ]
    bot.client.result = [{"command": "start", "description": "Start the bot"}]
    commands = bot.get_my_commands()
    assert commands[0].command == "start"
    bot.client.result = True
    bot.set_my_name("My Bot")
    assert recording_client.calls[-1]["method"] == "setMyName"


def test_inline_and_pre_checkout_answers(bot, recording_client):
    bot.client.result = True
    bot.answer_inline_query("q1", [{
        "type": "article", "id": "1", "title": "Result",
        "input_message_content": {"message_text": "hi"},
    }])
    params = recording_client.calls[0]["params"]
    assert recording_client.calls[0]["method"] == "answerInlineQuery"
    assert params["results"][0]["type"] == "article"
    bot.answer_pre_checkout_query("pc1", ok=True)
    assert recording_client.calls[1]["method"] == "answerPreCheckoutQuery"


def test_new_handler_decorators_route(bot):
    received = []

    @bot.inline_query_handler(func=lambda q: True)
    def inline(query):
        received.append(("inline", query.query))

    @bot.poll_handler(func=lambda p: True)
    def poll(poll_obj):
        received.append(("poll", poll_obj.id))

    @bot.my_chat_member_handler()
    def member(cm):
        received.append(("member", cm.new_chat_member.status))

    bot.process_new_updates([
        {"update_id": 1, "inline_query": {"id": "q", "from": {"id": 1, "is_bot": False, "first_name": "A"}, "query": "weather"}},
        {"update_id": 2, "poll": {"id": "p1", "question": "?", "options": []}},
        {"update_id": 3, "my_chat_member": {
            "chat": {"id": 1, "type": "private", "first_name": "A"},
            "from": {"id": 1, "is_bot": False, "first_name": "A"},
            "date": 1760000000,
            "old_chat_member": {"status": "member", "user": {"id": 1, "is_bot": False, "first_name": "A"}},
            "new_chat_member": {"status": "kicked", "user": {"id": 1, "is_bot": False, "first_name": "A"}},
        }},
    ])
    assert received == [("inline", "weather"), ("poll", "p1"), ("member", "kicked")]


def test_send_long_message_splits(bot, recording_client):
    bot.client.result = COMMAND_MESSAGE_JSON
    long_text = "hello\n\n" * 2000  # > 4096 chars
    messages = bot.send_long_message(1, long_text)
    assert len(messages) > 1
    assert all(c["method"] == "sendMessage" for c in recording_client.calls)
    assert all(len(c["params"]["text"]) <= 4096 for c in recording_client.calls)


def test_download_file_returns_bytes(recording_client, monkeypatch):
    bot = Bot(token=TOKEN, client=recording_client)
    bot.client.result = {"file_id": "x", "file_unique_id": "y", "file_path": "docs/a.txt"}
    file = bot.get_file("x")
    monkeypatch.setattr(bot.client, "get_bytes", lambda url, timeout=None: b"RAW", raising=False)
    assert bot.download_file(file) == b"RAW"


def test_threaded_dispatch_processes_updates(recording_client):
    bot = Bot(token=TOKEN, client=recording_client, threaded=True, num_workers=2)
    received = []

    @bot.message_handler(func=lambda m: True)
    def handler(message):
        received.append(message)

    bot.process_new_updates([UPDATE_JSON])
    bot._executor.shutdown(wait=True)  # wait for the worker to finish
    assert len(received) == 1


def test_stop_polling_sets_event(recording_client):
    bot = Bot(token=TOKEN, client=recording_client)
    assert not bot._stop_event.is_set()
    bot.stop_polling()
    assert bot._stop_event.is_set()


def test_parse_mode_default_is_applied(bot, recording_client):
    bot2 = Bot(token=TOKEN, client=recording_client, parse_mode="HTML")
    bot2.client.result = COMMAND_MESSAGE_JSON
    bot2.send_message(1, "<b>hi</b>")
    assert recording_client.calls[0]["params"]["parse_mode"] == "HTML"
    explicit = Bot(token=TOKEN, client=recording_client, parse_mode="HTML")
    explicit.client.result = COMMAND_MESSAGE_JSON
    explicit.send_message(1, "text", parse_mode="MarkdownV2")
    assert recording_client.calls[-1]["params"]["parse_mode"] == "MarkdownV2"


def test_bot_context_manager_closes(recording_client):
    with Bot(token=TOKEN, client=recording_client) as bot:
        assert bot.token == TOKEN
    assert bot._stop_event.is_set()
