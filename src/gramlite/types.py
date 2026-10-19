"""Telegram Bot API type definitions.

Every object Telegram sends back is parsed into a subclass of
:class:`TelegramObject`. Parsing is intentionally forgiving:

* unknown JSON fields are preserved as plain attributes,
* missing fields return ``None`` instead of raising ``AttributeError``,
* the only rename is ``Message.from`` → :attr:`Message.from_user`
  (``from`` is a reserved keyword in Python).

Request-side objects (the keyboards) are also defined here — they know how to
serialise themselves into the JSON shapes the Bot API expects.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "Animation", "Audio", "BotCommand", "CallbackQuery", "Chat",
    "ChatInviteLink", "ChatJoinRequest", "ChatMember", "ChatMemberUpdated",
    "ChatPermissions", "Contact", "Dice", "Document", "File", "ForceReply",
    "InlineKeyboardButton", "InlineKeyboardMarkup", "InlineQuery",
    "InputMediaPhoto", "InputMediaVideo", "Invoice", "KeyboardButton",
    "Location", "Message", "MessageEntity", "MessageId", "ParseMode",
    "PhotoSize", "Poll", "PollAnswer", "PollOption", "PreCheckoutQuery",
    "ReplyKeyboardMarkup", "ReplyKeyboardRemove", "Sticker",
    "SuccessfulPayment", "TelegramObject", "Update", "User",
    "UserProfilePhotos", "Venue", "Video", "VideoNote", "Voice",
    "WebhookInfo",
]


class ParseMode:
    """Parse modes accepted by Telegram for text formatting."""

    HTML = "HTML"
    MARKDOWN = "Markdown"
    MARKDOWN_V2 = "MarkdownV2"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class TelegramObject:
    """Base class for every Telegram type.

    Subclasses usually only need to override :meth:`de_json` when they contain
    nested objects that must be parsed recursively.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._raw: Dict[str, Any] = kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails: treat any unknown
        # API field as None instead of raising. Mirrors pyTelegramBotAPI's UX.
        if name.startswith("_"):
            raise AttributeError(name)
        return None

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["TelegramObject"]:
        """Build an instance from a Telegram JSON object (or return ``None``)."""
        if data is None:
            return None
        return cls(**data)

    @classmethod
    def de_list(cls, data: Optional[List[Dict[str, Any]]]) -> List["TelegramObject"]:
        """Build a list of instances from a Telegram JSON array."""
        return [cls.de_json(item) for item in (data or [])]

    def to_dict(self) -> Dict[str, Any]:
        """Serialise back to a JSON-compatible dict (drops private/None fields)."""

        def convert(value: Any) -> Any:
            if isinstance(value, TelegramObject):
                return value.to_dict()
            if isinstance(value, list):
                return [convert(item) for item in value]
            return value

        return {
            key: convert(value)
            for key, value in self.__dict__.items()
            if not key.startswith("_") and value is not None
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}({self.to_dict()!r})"


# ---------------------------------------------------------------------------
# Simple response types (straight pass-through)
# ---------------------------------------------------------------------------
class User(TelegramObject):
    """A Telegram user or bot: ``id``, ``is_bot``, ``first_name``,
    ``last_name``, ``username``, ``language_code``."""

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    def mention(self) -> str:
        """An HTML mention linking to this user's profile."""
        return f'<a href="tg://user?id={self.id}">{self.full_name or "user"}</a>'


class Chat(TelegramObject):
    """A chat: ``id``, ``type`` (``private``/``group``/``supergroup``/``channel``),
    ``title`` (groups), ``username``, ``first_name``/``last_name`` (private)."""

    @property
    def full_name(self) -> str:
        return self.title or " ".join(
            part for part in (self.first_name, self.last_name) if part
        )


class PhotoSize(TelegramObject):
    """One size of a photo: ``file_id``, ``file_unique_id``, ``width``, ``height``, ``file_size``."""


class Audio(TelegramObject):
    """An audio file: ``file_id``, ``duration``, ``performer``, ``title``, ``mime_type``, ``file_size``."""


class Document(TelegramObject):
    """A generic file: ``file_id``, ``file_unique_id``, ``file_name``, ``mime_type``, ``file_size``."""


class Video(TelegramObject):
    """A video file: ``file_id``, ``width``, ``height``, ``duration``, ``mime_type``, ``file_size``."""


class VideoNote(TelegramObject):
    """A round video note: ``file_id``, ``length``, ``duration``, ``file_size``."""


class Voice(TelegramObject):
    """A voice message: ``file_id``, ``duration``, ``mime_type``, ``file_size``."""


class Animation(TelegramObject):
    """A GIF animation (sent as a document): ``file_id``, ``file_name``, ``mime_type``, ``duration``."""


class Sticker(TelegramObject):
    """A sticker: ``file_id``, ``file_unique_id``, ``width``, ``height``, ``emoji``, ``is_animated``."""


class Location(TelegramObject):
    """A geographic point: ``latitude``, ``longitude``."""


class Contact(TelegramObject):
    """A phone contact: ``phone_number``, ``first_name``, ``last_name``, ``user_id``."""


class File(TelegramObject):
    """A file ready to download: ``file_id``, ``file_unique_id``, ``file_size``, ``file_path``."""


class WebhookInfo(TelegramObject):
    """Current webhook state: ``url``, ``has_custom_certificate``, ``pending_update_count``..."""


class MessageId(TelegramObject):
    """Returned by ``forwardMessage``/``copyMessage``: ``message_id``."""


class MessageEntity(TelegramObject):
    """A special entity in a message text (mention, hashtag, bot_command, url...):
    ``type``, ``offset``, ``length``, ``url``, ``user``."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["MessageEntity"]:
        if data is None:
            return None
        data = dict(data)
        data["user"] = User.de_json(data.get("user"))
        return cls(**data)


# ---------------------------------------------------------------------------
# Compound response types (recursive parsing)
# ---------------------------------------------------------------------------
class Message(TelegramObject):
    """A message. The central object of most bot logic.

    Commonly used attributes: ``message_id``, ``from_user``, ``chat``, ``date``,
    ``text``, ``caption``, ``entities``, ``reply_to_message``, ``photo``,
    ``audio``, ``document``, ``video``, ``voice``, ``sticker``, ``location``...

    :attr:`content_type` maps the message to a single human-friendly string
    (``"text"``, ``"photo"``, ...) that the handler system filters on.
    """

    # Checked in order when deriving ``content_type``.
    CONTENT_FIELDS = (
        "text", "audio", "document", "animation", "photo", "sticker",
        "video", "video_note", "voice", "location", "venue", "contact",
        "poll", "dice", "invoice", "successful_payment",
        "new_chat_members", "left_chat_member", "new_chat_title",
        "pinned_message",
    )

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["Message"]:
        if data is None:
            return None
        data = dict(data)
        # ``from`` is a Python keyword — expose it as ``from_user``.
        if "from" in data:
            data["from_user"] = User.de_json(data.pop("from"))
        data["chat"] = Chat.de_json(data.get("chat"))
        data["reply_to_message"] = Message.de_json(data.get("reply_to_message"))
        data["entities"] = MessageEntity.de_list(data.get("entities"))
        data["caption_entities"] = MessageEntity.de_list(data.get("caption_entities"))
        data["photo"] = PhotoSize.de_list(data.get("photo"))
        data["audio"] = Audio.de_json(data.get("audio"))
        data["document"] = Document.de_json(data.get("document"))
        data["animation"] = Animation.de_json(data.get("animation"))
        data["video"] = Video.de_json(data.get("video"))
        data["video_note"] = VideoNote.de_json(data.get("video_note"))
        data["voice"] = Voice.de_json(data.get("voice"))
        data["sticker"] = Sticker.de_json(data.get("sticker"))
        data["location"] = Location.de_json(data.get("location"))
        data["contact"] = Contact.de_json(data.get("contact"))
        data["venue"] = Venue.de_json(data.get("venue"))
        data["poll"] = Poll.de_json(data.get("poll"))
        data["dice"] = Dice.de_json(data.get("dice"))
        data["invoice"] = Invoice.de_json(data.get("invoice"))
        data["successful_payment"] = SuccessfulPayment.de_json(data.get("successful_payment"))
        data["left_chat_member"] = User.de_json(data.get("left_chat_member"))
        data["new_chat_members"] = User.de_list(data.get("new_chat_members"))
        data["pinned_message"] = Message.de_json(data.get("pinned_message"))
        return cls(**data)

    @property
    def content_type(self) -> str:
        """A single string describing what the message contains."""
        for field in self.CONTENT_FIELDS:
            if getattr(self, field) is not None:
                return field
        return "unknown"

    @property
    def is_command(self) -> bool:
        """True when the message text contains a ``/command`` entity."""
        return any(
            getattr(entity, "type", None) == "bot_command"
            for entity in (self.entities or [])
        )

    def extract_command(self) -> Optional[str]:
        """Return the command name (without slash and ``@bot`` suffix), if any."""
        if not self.is_command or not self.text:
            return None
        for entity in self.entities or []:
            if getattr(entity, "type", None) == "bot_command":
                raw = self.text[entity.offset:entity.offset + entity.length]
                return raw.lstrip("/").split("@", 1)[0].lower()
        return None


class CallbackQuery(TelegramObject):
    """An incoming callback from an inline keyboard button press:
    ``id``, ``from_user``, ``message``, ``data``, ``chat_instance``."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["CallbackQuery"]:
        if data is None:
            return None
        data = dict(data)
        if "from" in data:
            data["from_user"] = User.de_json(data.pop("from"))
        data["message"] = Message.de_json(data.get("message"))
        return cls(**data)


class Update(TelegramObject):
    """One incoming update from Telegram. Exactly one payload field is set
    (``message``, ``edited_message``, ``channel_post``, ``callback_query``...)."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["Update"]:
        if data is None:
            return None
        data = dict(data)
        data["message"] = Message.de_json(data.get("message"))
        data["edited_message"] = Message.de_json(data.get("edited_message"))
        data["channel_post"] = Message.de_json(data.get("channel_post"))
        data["edited_channel_post"] = Message.de_json(data.get("edited_channel_post"))
        data["callback_query"] = CallbackQuery.de_json(data.get("callback_query"))
        data["inline_query"] = InlineQuery.de_json(data.get("inline_query"))
        data["pre_checkout_query"] = PreCheckoutQuery.de_json(data.get("pre_checkout_query"))
        data["poll"] = Poll.de_json(data.get("poll"))
        data["poll_answer"] = PollAnswer.de_json(data.get("poll_answer"))
        data["my_chat_member"] = ChatMemberUpdated.de_json(data.get("my_chat_member"))
        data["chat_member"] = ChatMemberUpdated.de_json(data.get("chat_member"))
        data["chat_join_request"] = ChatJoinRequest.de_json(data.get("chat_join_request"))
        return cls(**data)

    @property
    def effective_message(self) -> Optional[Message]:
        """The message-like payload of this update, whichever kind it is."""
        if self.message is not None:
            return self.message
        if self.edited_message is not None:
            return self.edited_message
        if self.channel_post is not None:
            return self.channel_post
        if self.edited_channel_post is not None:
            return self.edited_channel_post
        if self.callback_query is not None:
            return self.callback_query.message
        return None


# ---------------------------------------------------------------------------
# Request-side types (keyboards) — built by users, serialised to JSON
# ---------------------------------------------------------------------------
class KeyboardButton(TelegramObject):
    """A button of a custom reply keyboard."""

    def __init__(
        self,
        text: str,
        request_contact: Optional[bool] = None,
        request_location: Optional[bool] = None,
    ) -> None:
        super().__init__(
            text=text,
            request_contact=request_contact,
            request_location=request_location,
        )


class _RowsMarkup(TelegramObject):
    """Shared row-building logic for the two keyboard families."""

    def __init__(self, row_width: int = 3) -> None:
        super().__init__()
        self.row_width = row_width
        self.rows: List[List[TelegramObject]] = []

    def add(self, *buttons: TelegramObject) -> "_RowsMarkup":
        """Append buttons, wrapping to a new row every ``row_width`` buttons."""
        for start in range(0, len(buttons), self.row_width):
            self.rows.append(list(buttons[start:start + self.row_width]))
        return self

    def row(self, *buttons: TelegramObject) -> "_RowsMarkup":
        """Append exactly one row containing the given buttons."""
        self.rows.append(list(buttons))
        return self


class ReplyKeyboardMarkup(_RowsMarkup):
    """A custom keyboard shown instead of the device keyboard."""

    def __init__(
        self,
        resize_keyboard: bool = False,
        one_time_keyboard: bool = False,
        selective: Optional[bool] = None,
        row_width: int = 3,
        input_field_placeholder: Optional[str] = None,
        is_persistent: Optional[bool] = None,
    ) -> None:
        super().__init__(row_width=row_width)
        self.resize_keyboard = resize_keyboard
        self.one_time_keyboard = one_time_keyboard
        self.selective = selective
        self.input_field_placeholder = input_field_placeholder
        self.is_persistent = is_persistent

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "keyboard": [[button.to_dict() for button in row] for row in self.rows],
            "resize_keyboard": self.resize_keyboard,
            "one_time_keyboard": self.one_time_keyboard,
            "selective": self.selective,
            "input_field_placeholder": self.input_field_placeholder,
            "is_persistent": self.is_persistent,
        }
        return {key: value for key, value in data.items() if value is not None}


class InlineKeyboardMarkup(_RowsMarkup):
    """An inline keyboard attached to a message, with callback buttons."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inline_keyboard": [
                [button.to_dict() for button in row] for row in self.rows
            ]
        }


class InlineKeyboardButton(TelegramObject):
    """A button of an :class:`InlineKeyboardMarkup`."""

    def __init__(
        self,
        text: str,
        callback_data: Optional[str] = None,
        url: Optional[str] = None,
    ) -> None:
        if not (callback_data or url):
            raise ValueError("InlineKeyboardButton needs 'callback_data' or 'url'.")
        super().__init__(text=text, callback_data=callback_data, url=url)


class ReplyKeyboardRemove(TelegramObject):
    """Remove the custom keyboard and restore the device keyboard."""

    def __init__(self, selective: Optional[bool] = None) -> None:
        super().__init__(selective=selective)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"remove_keyboard": True}
        if self.selective is not None:
            data["selective"] = self.selective
        return data


class ForceReply(TelegramObject):
    """Force the user to reply to the message (quasi-modal interaction)."""

    def __init__(
        self,
        input_field_placeholder: Optional[str] = None,
        selective: Optional[bool] = None,
    ) -> None:
        super().__init__(
            input_field_placeholder=input_field_placeholder,
            selective=selective,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"force_reply": True}
        if self.input_field_placeholder is not None:
            data["input_field_placeholder"] = self.input_field_placeholder
        if self.selective is not None:
            data["selective"] = self.selective
        return data


# ---------------------------------------------------------------------------
# v2 types — polls, moderation, payments, inline mode
# ---------------------------------------------------------------------------
class Dice(TelegramObject):
    """A dice animation: ``emoji`` (🎲 🎯 🏀 ...) and the drawn ``value`` (1-6 or 1-64)."""


class PollOption(TelegramObject):
    """One option of a poll: ``text`` and ``voter_count``."""


class Poll(TelegramObject):
    """A native poll: ``id``, ``question``, ``options``, ``is_closed``, ``type``..."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["Poll"]:
        if data is None:
            return None
        data = dict(data)
        data["options"] = PollOption.de_list(data.get("options"))
        return cls(**data)


class PollAnswer(TelegramObject):
    """A user's answer to a poll: ``poll_id``, ``user``, ``option_ids``."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["PollAnswer"]:
        if data is None:
            return None
        data = dict(data)
        data["user"] = User.de_json(data.get("user"))
        return cls(**data)


class Venue(TelegramObject):
    """A venue: ``location``, ``title``, ``address`` (plus optional Foursquare ids)."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["Venue"]:
        if data is None:
            return None
        data = dict(data)
        data["location"] = Location.de_json(data.get("location"))
        return cls(**data)


class Invoice(TelegramObject):
    """A payment invoice: ``title``, ``description``, ``currency``, ``total_amount``."""


class SuccessfulPayment(TelegramObject):
    """A completed payment: ``currency``, ``total_amount``, ``invoice_payload``,
    ``telegram_payment_charge_id``..."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["SuccessfulPayment"]:
        if data is None:
            return None
        data = dict(data)
        data["order_info"] = TelegramObject.de_json(data.get("order_info"))
        return cls(**data)


class PreCheckoutQuery(TelegramObject):
    """A payment pre-checkout query — must be answered within 10 seconds."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["PreCheckoutQuery"]:
        if data is None:
            return None
        data = dict(data)
        data["from_user"] = User.de_json(data.pop("from", None))
        data["order_info"] = TelegramObject.de_json(data.get("order_info"))
        return cls(**data)


class InlineQuery(TelegramObject):
    """An inline query typed in a foreign chat: ``id``, ``from_user``, ``query``, ``offset``."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["InlineQuery"]:
        if data is None:
            return None
        data = dict(data)
        data["from_user"] = User.de_json(data.pop("from", None))
        data["location"] = Location.de_json(data.get("location"))
        return cls(**data)


class ChatPermissions(TelegramObject):
    """What members are allowed to do: ``can_send_messages``, ``can_invite_users``...
    Any field left as ``None`` is omitted (defaults to the API's semantics)."""

    def __init__(
        self,
        can_send_messages: Optional[bool] = None,
        can_send_audios: Optional[bool] = None,
        can_send_documents: Optional[bool] = None,
        can_send_photos: Optional[bool] = None,
        can_send_videos: Optional[bool] = None,
        can_send_video_notes: Optional[bool] = None,
        can_send_voice_notes: Optional[bool] = None,
        can_send_polls: Optional[bool] = None,
        can_send_other_messages: Optional[bool] = None,
        can_add_web_page_previews: Optional[bool] = None,
        can_change_info: Optional[bool] = None,
        can_invite_users: Optional[bool] = None,
        can_pin_messages: Optional[bool] = None,
        can_manage_topics: Optional[bool] = None,
    ) -> None:
        super().__init__(**{
            "can_send_messages": can_send_messages,
            "can_send_audios": can_send_audios,
            "can_send_documents": can_send_documents,
            "can_send_photos": can_send_photos,
            "can_send_videos": can_send_videos,
            "can_send_video_notes": can_send_video_notes,
            "can_send_voice_notes": can_send_voice_notes,
            "can_send_polls": can_send_polls,
            "can_send_other_messages": can_send_other_messages,
            "can_add_web_page_previews": can_add_web_page_previews,
            "can_change_info": can_change_info,
            "can_invite_users": can_invite_users,
            "can_pin_messages": can_pin_messages,
            "can_manage_topics": can_manage_topics,
        })


class ChatMember(TelegramObject):
    """A member of a chat with ``status``: creator/administrator/member/
    restricted/left/kicked, plus the permission flags of that role."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["ChatMember"]:
        if data is None:
            return None
        data = dict(data)
        data["user"] = User.de_json(data.get("user"))
        return cls(**data)


class ChatMemberUpdated(TelegramObject):
    """A membership change event: ``chat``, ``from_user``, ``old_chat_member``,
    ``new_chat_member`` (used by ``my_chat_member`` / ``chat_member`` updates)."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["ChatMemberUpdated"]:
        if data is None:
            return None
        data = dict(data)
        data["chat"] = Chat.de_json(data.get("chat"))
        data["from_user"] = User.de_json(data.pop("from", None))
        data["old_chat_member"] = ChatMember.de_json(data.get("old_chat_member"))
        data["new_chat_member"] = ChatMember.de_json(data.get("new_chat_member"))
        data["invite_link"] = ChatInviteLink.de_json(data.get("invite_link"))
        return cls(**data)


class ChatInviteLink(TelegramObject):
    """An invite link: ``invite_link``, ``creator``, ``expire_date``, ``member_limit``..."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["ChatInviteLink"]:
        if data is None:
            return None
        data = dict(data)
        data["creator"] = User.de_json(data.get("creator"))
        return cls(**data)


class ChatJoinRequest(TelegramObject):
    """A pending request to join a chat that requires approval."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["ChatJoinRequest"]:
        if data is None:
            return None
        data = dict(data)
        data["chat"] = Chat.de_json(data.get("chat"))
        data["from_user"] = User.de_json(data.pop("from", None))
        data["invite_link"] = ChatInviteLink.de_json(data.get("invite_link"))
        return cls(**data)


class BotCommand(TelegramObject):
    """A bot command advertised in the Telegram UI: ``command`` (no slash) and
    ``description`` (3-256 chars). Tuples/lists of two strings are accepted too
    by ``set_my_commands``."""

    def __init__(self, command: str, description: str) -> None:
        super().__init__(command=command, description=description)

    @classmethod
    def de_list(cls, data):  # type: ignore[override]
        """Accepts ``[("start", "Start the bot"), ...]`` as well as dicts."""
        if data is None:
            return []
        items = []
        for item in data:
            if isinstance(item, TelegramObject):
                items.append(item)
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                items.append(BotCommand(item[0], item[1]))
            elif isinstance(item, dict):
                items.append(BotCommand(item["command"], item["description"]))
        return items


class UserProfilePhotos(TelegramObject):
    """A user's profile pictures: ``total_count`` and ``photos`` (arrays of
    :class:`PhotoSize`, one array per picture)."""

    @classmethod
    def de_json(cls, data: Optional[Dict[str, Any]]) -> Optional["UserProfilePhotos"]:
        if data is None:
            return None
        data = dict(data)
        data["photos"] = [PhotoSize.de_list(row) for row in (data.get("photos") or [])]
        return cls(**data)


class InputMedia(TelegramObject):
    """Base for photos/videos inside :meth:`Bot.send_media_group`."""

    def __init__(self, media_type: str, media: str, caption: Optional[str] = None,
                 parse_mode: Optional[str] = None) -> None:
        super().__init__(type=media_type, media=media, caption=caption, parse_mode=parse_mode)


class InputMediaPhoto(InputMedia):
    def __init__(self, media: str, caption: Optional[str] = None, parse_mode: Optional[str] = None) -> None:
        super().__init__("photo", media, caption, parse_mode)


class InputMediaVideo(InputMedia):
    def __init__(self, media: str, caption: Optional[str] = None, parse_mode: Optional[str] = None,
                 supports_streaming: Optional[bool] = None) -> None:
        super().__init__("video", media, caption, parse_mode)
        self.supports_streaming = supports_streaming
