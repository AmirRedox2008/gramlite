"""GramLite — a lightweight, from-scratch Telegram Bot API framework.

Both a synchronous and an asynchronous API are provided. The async extra is
optional, so :class:`AsyncBot` is imported lazily and only requires
``aiohttp`` when actually used::

    pip install gramlite           # sync only (requests)
    pip install "gramlite[async]"  # + async support (aiohttp)
    pip install "gramlite[redis]"  # + Redis FSM storage
"""

from __future__ import annotations

from . import types
from .api_client import APIClient
from .bot import Bot
from .exceptions import (
    ApiHTTPError,
    ApiTelegramError,
    BotBlockedError,
    InvalidTokenError,
    NetworkError,
    RateLimitError,
    TelegramError,
)
from .fsm import BaseStorage, JSONFileStorage, MemoryStorage, State, StateGroup
from .handlers import (
    CONTENT_TYPES,
    CHAT_TYPES,
    AsyncHandlerRegistry,
    BaseFilter,
    Handler,
    HandlerRegistry,
)
from .log import setup_logging
from .middleware import AsyncMiddlewareManager, MiddlewareManager
from .types import (
    Animation,
    Audio,
    BotCommand,
    CallbackQuery,
    Chat,
    ChatInviteLink,
    ChatJoinRequest,
    ChatMember,
    ChatMemberUpdated,
    ChatPermissions,
    Contact,
    Dice,
    Document,
    File,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InputMediaPhoto,
    InputMediaVideo,
    Invoice,
    KeyboardButton,
    Location,
    Message,
    MessageEntity,
    MessageId,
    ParseMode,
    PhotoSize,
    Poll,
    PollAnswer,
    PollOption,
    PreCheckoutQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Sticker,
    SuccessfulPayment,
    TelegramObject,
    Update,
    User,
    UserProfilePhotos,
    Venue,
    Video,
    VideoNote,
    Voice,
    WebhookInfo,
)
from .utils import (
    create_deep_link,
    escape_html,
    escape_markdown,
    split_text,
)

__version__ = "2.0.0"

__all__ = [
    # bots & plumbing
    "APIClient", "AsyncBot", "AsyncHandlerRegistry", "AsyncMiddlewareManager",
    "BaseFilter", "Bot", "Handler", "HandlerRegistry", "MiddlewareManager",
    # errors
    "ApiHTTPError", "ApiTelegramError", "BotBlockedError", "InvalidTokenError",
    "NetworkError", "RateLimitError", "TelegramError",
    # fsm
    "BaseStorage", "JSONFileStorage", "MemoryStorage", "State", "StateGroup",
    # types
    "Animation", "Audio", "BotCommand", "CallbackQuery", "CHAT_TYPES",
    "CONTENT_TYPES", "Chat", "ChatInviteLink", "ChatJoinRequest", "ChatMember",
    "ChatMemberUpdated", "ChatPermissions", "Contact", "Dice", "Document",
    "File", "ForceReply", "InlineKeyboardButton", "InlineKeyboardMarkup",
    "InlineQuery", "InputMediaPhoto", "InputMediaVideo", "Invoice",
    "KeyboardButton", "Location", "Message", "MessageEntity", "MessageId",
    "ParseMode", "PhotoSize", "Poll", "PollAnswer", "PollOption",
    "PreCheckoutQuery", "ReplyKeyboardMarkup", "ReplyKeyboardRemove",
    "Sticker", "SuccessfulPayment", "TelegramObject", "Update", "User",
    "UserProfilePhotos", "Venue", "Video", "VideoNote", "Voice", "WebhookInfo",
    # utils
    "create_deep_link", "escape_html", "escape_markdown", "setup_logging",
    "split_text", "types", "__version__",
]

_MODULE_ALIASES = {
    "TelegramBot": "Bot",  # familiar alias for pyTelegramBotAPI users
}


def __getattr__(name: str):
    """Lazily expose the optional async stack (PEP 562)."""
    if name == "AsyncBot":
        from .async_bot import AsyncBot  # noqa: PLC0415 - deliberate lazy import
        return AsyncBot
    if name in _MODULE_ALIASES:
        import sys  # noqa: PLC0415
        return getattr(sys.modules[__name__], _MODULE_ALIASES[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | {"AsyncBot"})
