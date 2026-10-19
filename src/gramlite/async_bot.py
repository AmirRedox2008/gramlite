"""The asynchronous :class:`AsyncBot` — aiohttp-based twin of :class:`Bot`.

Design notes
------------
* The HTTP transport (:class:`AsyncAPIClient`) mirrors the sync client but is
  ``async`` end-to-end and uses ``aiohttp``.
* Types and filters are **shared** with the sync bot; only the dispatcher
  differs (:class:`~gramlite.handlers.AsyncHandlerRegistry`) so that
  ``async def`` handlers and middleware are genuinely awaited.
* ``aiohttp`` is an optional dependency: importing this module without it
  raises a helpful installation hint.

Example::

    import asyncio
    from gramlite import AsyncBot

    bot = AsyncBot("TOKEN")

    @bot.message_handler(commands=["start"])
    async def welcome(message):
        await bot.reply_to(message, "Hello!")

    asyncio.run(bot.infinity_polling())
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

try:
    import aiohttp
except ImportError as exc:  # pragma: no cover - environment dependent
    raise ImportError(
        "AsyncBot requires aiohttp. Install it with:  pip install 'gramlite[async]'"
    ) from exc

from .api_client import _api_error, prepare_params
from .exceptions import ApiHTTPError, ApiTelegramError, NetworkError
from .fsm import BaseStorage, MemoryStorage, State, state_full_name
from .handlers import AsyncHandlerRegistry, HandlerRegistrationMixin
from .middleware import AsyncMiddlewareManager
from .types import (
    BotCommand,
    Chat,
    ChatInviteLink,
    ChatMember,
    ChatPermissions,
    File,
    Message,
    MessageId,
    Poll,
    TelegramObject,
    Update,
    User,
    UserProfilePhotos,
    WebhookInfo,
)
from .utils import split_text

logger = logging.getLogger("gramlite.async")

__all__ = ["AsyncAPIClient", "AsyncBot"]


class AsyncAPIClient:
    """Asynchronous low-level client for the Telegram Bot API."""

    DEFAULT_BASE_URL = "https://api.telegram.org"

    def __init__(
        self,
        token: str,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        if not token:
            raise ValueError("A bot token is required (get one from @BotFather).")
        self.token = token
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._session = session

    # ------------------------------------------------------------------ urls
    @property
    def api_url(self) -> str:
        return f"{self.base_url}/bot{self.token}"

    def file_download_url(self, file_path: str) -> str:
        return f"{self.base_url}/file/bot{self.token}/{file_path}"

    # --------------------------------------------------------------- session
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    # --------------------------------------------------------------- request
    async def request(
        self,
        method_name: str,
        params: Optional[Dict[str, Any]] = None,
        files: Optional["aiohttp.FormData"] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = f"{self.api_url}/{method_name}"
        data = files if files is not None else prepare_params(params)
        attempt = 0

        while True:
            session = await self._get_session()
            try:
                async with session.post(
                    url,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=timeout or self.timeout),
                ) as response:
                    status = response.status
                    try:
                        body = await response.json(content_type=None)
                    except (ValueError, aiohttp.ContentTypeError):
                        body = None
            except aiohttp.ClientError as exc:
                raise NetworkError(f"Network failure while calling {method_name}: {exc}") from exc

            retryable = status == 429 or status >= 500
            if retryable and attempt < self.max_retries:
                delay = self._retry_delay(body, status, attempt)
                logger.warning(
                    "HTTP %s from %s — retrying in %.1fs (attempt %d/%d)",
                    status, method_name, delay, attempt + 1, self.max_retries,
                )
                attempt += 1
                await asyncio.sleep(delay)
                continue

            return self._parse(method_name, body, status)

    # ------------------------------------------------------------ internals
    def _retry_delay(self, body: Optional[dict], status: int, attempt: int) -> float:
        if isinstance(body, dict):
            retry_after = (body.get("parameters") or {}).get("retry_after")
            if retry_after:
                return float(retry_after)
        return self.backoff_factor * (2 ** attempt)

    @staticmethod
    def _parse(method_name: str, body: Optional[dict], status: int) -> Any:
        if body is None:
            if status != 200:
                raise ApiHTTPError(status, method_name)
            raise NetworkError(f"Malformed (non-JSON) response from {method_name}")

        if body.get("ok"):
            return body.get("result")

        raise _api_error(method_name, body, status)

    # ---------------------------------------------------------------- files
    async def get_bytes(self, url: str, timeout: Optional[float] = None) -> bytes:
        """Download a raw file (e.g. from :meth:`file_download_url`)."""
        session = await self._get_session()
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout or self.timeout)
            ) as response:
                if response.status != 200:
                    raise ApiHTTPError(response.status, "file download")
                return await response.read()
        except aiohttp.ClientError as exc:
            raise NetworkError(f"Network failure while downloading file: {exc}") from exc


class AsyncBot(HandlerRegistrationMixin):
    """An asynchronous Telegram bot with the same surface as :class:`Bot`."""

    def __init__(
        self,
        token: str,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        client: Optional[AsyncAPIClient] = None,
        storage: Optional[BaseStorage] = None,
        parse_mode: Optional[str] = None,
        bot_username: Optional[str] = None,
    ) -> None:
        self.client = client or AsyncAPIClient(
            token=token, base_url=base_url, timeout=timeout, max_retries=max_retries
        )
        self.router = AsyncHandlerRegistry()
        self.router.bot_username = bot_username
        self.middleware = AsyncMiddlewareManager()
        self.router.middleware = self.middleware
        self.storage: BaseStorage = storage or MemoryStorage()
        self.parse_mode = parse_mode

    # ------------------------------------------------------------- lifecycle
    @property
    def token(self) -> str:
        return self.client.token

    # async-context-manager support: `async with AsyncBot(token) as bot: ...`
    async def __aenter__(self) -> "AsyncBot":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.close()

    # ==================================================================
    # Updates
    # ==================================================================
    async def get_updates(
        self,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        timeout: Optional[int] = 0,
        allowed_updates: Optional[Iterable[str]] = None,
    ) -> List[Update]:
        params: Dict[str, Any] = {"offset": offset, "limit": limit, "timeout": timeout}
        if allowed_updates is not None:
            params["allowed_updates"] = json.dumps(list(allowed_updates))
        result = await self.client.request("getUpdates", params)
        return Update.de_list(result)  # type: ignore[return-value]

    async def set_webhook(
        self,
        url: str,
        drop_pending_updates: Optional[bool] = None,
        allowed_updates: Optional[Iterable[str]] = None,
        secret_token: Optional[str] = None,
        max_connections: Optional[int] = None,
    ) -> bool:
        params: Dict[str, Any] = {
            "url": url, "drop_pending_updates": drop_pending_updates,
            "secret_token": secret_token, "max_connections": max_connections,
        }
        if allowed_updates is not None:
            params["allowed_updates"] = json.dumps(list(allowed_updates))
        return await self.client.request("setWebhook", params)

    async def delete_webhook(self, drop_pending_updates: Optional[bool] = None) -> bool:
        return await self.client.request("deleteWebhook", {"drop_pending_updates": drop_pending_updates})

    async def get_webhook_info(self) -> WebhookInfo:
        return WebhookInfo.de_json(await self.client.request("getWebhookInfo"))  # type: ignore[return-value]

    # ==================================================================
    # Profile & chat info
    # ==================================================================
    async def get_me(self) -> User:
        return User.de_json(await self.client.request("getMe"))  # type: ignore[return-value]

    async def get_chat(self, chat_id: Union[int, str]) -> Chat:
        return Chat.de_json(await self.client.request("getChat", {"chat_id": chat_id}))  # type: ignore[return-value]

    async def get_chat_member_count(self, chat_id: Union[int, str]) -> int:
        return await self.client.request("getChatMemberCount", {"chat_id": chat_id})

    async def get_chat_member(self, chat_id: Union[int, str], user_id: int) -> ChatMember:
        return ChatMember.de_json(await self.client.request("getChatMember", {
            "chat_id": chat_id, "user_id": user_id,
        }))  # type: ignore[return-value]

    async def get_chat_administrators(self, chat_id: Union[int, str]) -> List[ChatMember]:
        result = await self.client.request("getChatAdministrators", {"chat_id": chat_id})
        return ChatMember.de_list(result)  # type: ignore[return-value]

    async def get_user_profile_photos(
        self, user_id: int, offset: Optional[int] = None, limit: Optional[int] = None
    ) -> UserProfilePhotos:
        return UserProfilePhotos.de_json(await self.client.request("getUserProfilePhotos", {
            "user_id": user_id, "offset": offset, "limit": limit,
        }))  # type: ignore[return-value]

    # ==================================================================
    # Messaging
    # ==================================================================
    async def send_message(
        self,
        chat_id: Union[int, str],
        text: str,
        parse_mode: Optional[str] = None,
        entities: Optional[List[dict]] = None,
        disable_web_page_preview: Optional[bool] = None,
        disable_notification: Optional[bool] = None,
        protect_content: Optional[bool] = None,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        return Message.de_json(await self.client.request("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode or self.parse_mode,
            "entities": entities,
            "disable_web_page_preview": disable_web_page_preview,
            "disable_notification": disable_notification,
            "protect_content": protect_content,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def reply_to(self, message: Message, text: str, **kwargs: Any) -> Message:
        return await self.send_message(
            message.chat.id, text, reply_to_message_id=message.message_id, **kwargs
        )

    async def send_long_message(
        self, chat_id: Union[int, str], text: str, **kwargs: Any
    ) -> List[Message]:
        """Send a text of any length — automatically split at 4096 chars."""
        return [
            await self.send_message(chat_id, chunk, **kwargs)
            for chunk in split_text(text)
        ]

    async def edit_message_text(
        self,
        text: str,
        chat_id: Optional[Union[int, str]] = None,
        message_id: Optional[int] = None,
        inline_message_id: Optional[str] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Union[Message, bool]:
        result = await self.client.request("editMessageText", {
            "text": text,
            "chat_id": chat_id,
            "message_id": message_id,
            "inline_message_id": inline_message_id,
            "parse_mode": parse_mode or self.parse_mode,
            "reply_markup": reply_markup,
        })
        return True if result is True else Message.de_json(result)  # type: ignore[return-value]

    async def edit_message_caption(
        self,
        chat_id: Optional[Union[int, str]] = None,
        message_id: Optional[int] = None,
        inline_message_id: Optional[str] = None,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Union[Message, bool]:
        result = await self.client.request("editMessageCaption", {
            "chat_id": chat_id, "message_id": message_id,
            "inline_message_id": inline_message_id, "caption": caption,
            "parse_mode": parse_mode or self.parse_mode, "reply_markup": reply_markup,
        })
        return True if result is True else Message.de_json(result)  # type: ignore[return-value]

    async def edit_message_reply_markup(
        self,
        chat_id: Optional[Union[int, str]] = None,
        message_id: Optional[int] = None,
        inline_message_id: Optional[str] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Union[Message, bool]:
        result = await self.client.request("editMessageReplyMarkup", {
            "chat_id": chat_id, "message_id": message_id,
            "inline_message_id": inline_message_id, "reply_markup": reply_markup,
        })
        return True if result is True else Message.de_json(result)  # type: ignore[return-value]

    async def delete_message(self, chat_id: Union[int, str], message_id: int) -> bool:
        return await self.client.request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    async def forward_message(
        self,
        chat_id: Union[int, str],
        from_chat_id: Union[int, str],
        message_id: int,
        disable_notification: Optional[bool] = None,
        protect_content: Optional[bool] = None,
    ) -> MessageId:
        return MessageId.de_json(await self.client.request("forwardMessage", {
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "message_id": message_id,
            "disable_notification": disable_notification,
            "protect_content": protect_content,
        }))  # type: ignore[return-value]

    async def copy_message(
        self,
        chat_id: Union[int, str],
        from_chat_id: Union[int, str],
        message_id: int,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> MessageId:
        return MessageId.de_json(await self.client.request("copyMessage", {
            "chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id,
            "caption": caption, "parse_mode": parse_mode or self.parse_mode,
            "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def send_chat_action(self, chat_id: Union[int, str], action: str) -> bool:
        return await self.client.request("sendChatAction", {"chat_id": chat_id, "action": action})

    async def pin_chat_message(
        self, chat_id: Union[int, str], message_id: int,
        disable_notification: Optional[bool] = None,
    ) -> bool:
        return await self.client.request("pinChatMessage", {
            "chat_id": chat_id, "message_id": message_id,
            "disable_notification": disable_notification,
        })

    async def unpin_chat_message(
        self, chat_id: Union[int, str], message_id: Optional[int] = None
    ) -> bool:
        return await self.client.request("unpinChatMessage", {
            "chat_id": chat_id, "message_id": message_id,
        })

    # ==================================================================
    # Media (shared FormData-based uploader)
    # ==================================================================
    async def send_photo(self, chat_id, photo, caption=None, parse_mode=None, **kwargs: Any) -> Message:
        return await self._send_media("photo", "sendPhoto", chat_id, photo, caption=caption,
                                      parse_mode=parse_mode, **kwargs)

    async def send_video(self, chat_id, video, caption=None, parse_mode=None, **kwargs: Any) -> Message:
        return await self._send_media("video", "sendVideo", chat_id, video, caption=caption,
                                      parse_mode=parse_mode, **kwargs)

    async def send_audio(self, chat_id, audio, caption=None, parse_mode=None, **kwargs: Any) -> Message:
        return await self._send_media("audio", "sendAudio", chat_id, audio, caption=caption,
                                      parse_mode=parse_mode, **kwargs)

    async def send_voice(self, chat_id, voice, caption=None, parse_mode=None, **kwargs: Any) -> Message:
        return await self._send_media("voice", "sendVoice", chat_id, voice, caption=caption,
                                      parse_mode=parse_mode, **kwargs)

    async def send_document(self, chat_id, document, caption=None, parse_mode=None, **kwargs: Any) -> Message:
        return await self._send_media("document", "sendDocument", chat_id, document, caption=caption,
                                      parse_mode=parse_mode, **kwargs)

    async def send_animation(self, chat_id, animation, caption=None, parse_mode=None, **kwargs: Any) -> Message:
        return await self._send_media("animation", "sendAnimation", chat_id, animation, caption=caption,
                                      parse_mode=parse_mode, **kwargs)

    async def send_video_note(self, chat_id, video_note, **kwargs: Any) -> Message:
        return await self._send_media("video_note", "sendVideoNote", chat_id, video_note, **kwargs)

    async def send_sticker(self, chat_id, sticker, **kwargs: Any) -> Message:
        return await self._send_media("sticker", "sendSticker", chat_id, sticker, **kwargs)

    async def _send_media(
        self,
        kind: str,
        method: str,
        chat_id: Union[int, str],
        media: Any,
        caption: Optional[str] = None,
        parse_mode: Optional[str] = None,
        disable_notification: Optional[bool] = None,
        protect_content: Optional[bool] = None,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        params: Dict[str, Any] = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": parse_mode or self.parse_mode,
            "disable_notification": disable_notification,
            "protect_content": protect_content,
            "reply_to_message_id": reply_to_message_id,
            "reply_markup": reply_markup,
        }
        result: Any
        opened = None
        try:
            if isinstance(media, str):
                params[kind] = media
                result = await self.client.request(method, params)
            else:
                form = aiohttp.FormData()
                for key, value in prepare_params(params).items():
                    form.add_field(key, str(value))
                if hasattr(media, "read"):
                    name = os.path.basename(getattr(media, "name", "") or "upload")
                    form.add_field(kind, media, filename=name)
                else:  # filesystem path
                    opened = open(str(media), "rb")
                    form.add_field(kind, opened, filename=os.path.basename(str(media)))
                result = await self.client.request(method, files=form)
        finally:
            if opened is not None:
                opened.close()
        return Message.de_json(result)  # type: ignore[return-value]

    async def send_media_group(
        self,
        chat_id: Union[int, str],
        media: Sequence[TelegramObject],
        disable_notification: Optional[bool] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> List[Message]:
        result = await self.client.request("sendMediaGroup", {
            "chat_id": chat_id,
            "media": [item.to_dict() for item in media],
            "disable_notification": disable_notification,
            "reply_to_message_id": reply_to_message_id,
        })
        return Message.de_list(result)  # type: ignore[return-value]

    # ==================================================================
    # Location, contact, polls, dice
    # ==================================================================
    async def send_location(
        self,
        chat_id: Union[int, str],
        latitude: float,
        longitude: float,
        disable_notification: Optional[bool] = None,
        reply_to_message_id: Optional[int] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        return Message.de_json(await self.client.request("sendLocation", {
            "chat_id": chat_id, "latitude": latitude, "longitude": longitude,
            "disable_notification": disable_notification,
            "reply_to_message_id": reply_to_message_id, "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def send_venue(
        self, chat_id: Union[int, str], latitude: float, longitude: float,
        title: str, address: str, reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        return Message.de_json(await self.client.request("sendVenue", {
            "chat_id": chat_id, "latitude": latitude, "longitude": longitude,
            "title": title, "address": address, "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def send_contact(
        self, chat_id: Union[int, str], phone_number: str, first_name: str,
        last_name: Optional[str] = None, reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        return Message.de_json(await self.client.request("sendContact", {
            "chat_id": chat_id, "phone_number": phone_number,
            "first_name": first_name, "last_name": last_name,
            "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def send_poll(
        self,
        chat_id: Union[int, str],
        question: str,
        options: Sequence[str],
        is_anonymous: Optional[bool] = None,
        allows_multiple_answers: Optional[bool] = None,
        poll_type: Optional[str] = None,
        correct_option_id: Optional[int] = None,
        explanation: Optional[str] = None,
        is_closed: Optional[bool] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        return Message.de_json(await self.client.request("sendPoll", {
            "chat_id": chat_id, "question": question, "options": list(options),
            "is_anonymous": is_anonymous,
            "allows_multiple_answers": allows_multiple_answers,
            "type": poll_type, "correct_option_id": correct_option_id,
            "explanation": explanation, "is_closed": is_closed,
            "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def stop_poll(
        self, chat_id: Union[int, str], message_id: int,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Poll:
        return Poll.de_json(await self.client.request("stopPoll", {
            "chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    async def send_dice(
        self, chat_id: Union[int, str], emoji: Optional[str] = None,
        reply_markup: Optional[TelegramObject] = None,
    ) -> Message:
        return Message.de_json(await self.client.request("sendDice", {
            "chat_id": chat_id, "emoji": emoji, "reply_markup": reply_markup,
        }))  # type: ignore[return-value]

    # ==================================================================
    # Callbacks, inline mode, payments
    # ==================================================================
    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: Optional[bool] = None,
        url: Optional[str] = None,
        cache_time: Optional[int] = None,
    ) -> bool:
        return await self.client.request("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
            "text": text, "show_alert": show_alert, "url": url, "cache_time": cache_time,
        })

    async def answer_inline_query(
        self,
        inline_query_id: str,
        results: Sequence[Any],
        cache_time: Optional[int] = None,
        is_personal: Optional[bool] = None,
        next_offset: Optional[str] = None,
    ) -> bool:
        payload = [
            item.to_dict() if isinstance(item, TelegramObject) else dict(item)
            for item in results
        ]
        return await self.client.request("answerInlineQuery", {
            "inline_query_id": inline_query_id, "results": payload,
            "cache_time": cache_time, "is_personal": is_personal,
            "next_offset": next_offset,
        })

    async def answer_pre_checkout_query(
        self, pre_checkout_query_id: str, ok: bool, error_message: Optional[str] = None
    ) -> bool:
        return await self.client.request("answerPreCheckoutQuery", {
            "pre_checkout_query_id": pre_checkout_query_id,
            "ok": ok, "error_message": error_message,
        })

    # ==================================================================
    # Files
    # ==================================================================
    async def get_file(self, file_id: str) -> File:
        return File.de_json(await self.client.request("getFile", {"file_id": file_id}))  # type: ignore[return-value]

    def download_file_url(self, file_or_path: Union[File, str]) -> str:
        file_path = getattr(file_or_path, "file_path", None) or str(file_or_path)
        return self.client.file_download_url(file_path)

    async def download_file(self, file_or_path: Union[File, str], timeout: Optional[float] = None) -> bytes:
        """Download a file's content as ``bytes`` (``getFile`` + fetch)."""
        file_path = getattr(file_or_path, "file_path", None) or str(file_or_path)
        return await self.client.get_bytes(self.download_file_url(file_path), timeout=timeout)

    # ==================================================================
    # Moderation
    # ==================================================================
    async def ban_chat_member(
        self, chat_id: Union[int, str], user_id: int,
        until_date: Optional[int] = None, revoke_messages: Optional[bool] = None,
    ) -> bool:
        return await self.client.request("banChatMember", {
            "chat_id": chat_id, "user_id": user_id,
            "until_date": until_date, "revoke_messages": revoke_messages,
        })

    async def unban_chat_member(
        self, chat_id: Union[int, str], user_id: int, only_if_banned: Optional[bool] = None
    ) -> bool:
        return await self.client.request("unbanChatMember", {
            "chat_id": chat_id, "user_id": user_id, "only_if_banned": only_if_banned,
        })

    async def restrict_chat_member(
        self, chat_id: Union[int, str], user_id: int,
        permissions: ChatPermissions, until_date: Optional[int] = None,
    ) -> bool:
        return await self.client.request("restrictChatMember", {
            "chat_id": chat_id, "user_id": user_id,
            "permissions": permissions, "until_date": until_date,
        })

    async def promote_chat_member(
        self, chat_id: Union[int, str], user_id: int, **privileges: Optional[bool]
    ) -> bool:
        return await self.client.request("promoteChatMember", {
            "chat_id": chat_id, "user_id": user_id, **privileges,
        })

    async def set_chat_title(self, chat_id: Union[int, str], title: str) -> bool:
        return await self.client.request("setChatTitle", {"chat_id": chat_id, "title": title})

    async def set_chat_description(
        self, chat_id: Union[int, str], description: Optional[str] = None
    ) -> bool:
        return await self.client.request("setChatDescription", {
            "chat_id": chat_id, "description": description,
        })

    async def set_chat_permissions(
        self, chat_id: Union[int, str], permissions: ChatPermissions
    ) -> bool:
        return await self.client.request("setChatPermissions", {
            "chat_id": chat_id, "permissions": permissions,
        })

    async def leave_chat(self, chat_id: Union[int, str]) -> bool:
        return await self.client.request("leaveChat", {"chat_id": chat_id})

    # ------------------------------------------------------- invite links
    async def export_chat_invite_link(self, chat_id: Union[int, str]) -> str:
        return await self.client.request("exportChatInviteLink", {"chat_id": chat_id})

    async def create_chat_invite_link(
        self, chat_id: Union[int, str], name: Optional[str] = None,
        expire_date: Optional[int] = None, member_limit: Optional[int] = None,
        creates_join_request: Optional[bool] = None,
    ) -> ChatInviteLink:
        return ChatInviteLink.de_json(await self.client.request("createChatInviteLink", {
            "chat_id": chat_id, "name": name, "expire_date": expire_date,
            "member_limit": member_limit, "creates_join_request": creates_join_request,
        }))  # type: ignore[return-value]

    async def revoke_chat_invite_link(
        self, chat_id: Union[int, str], invite_link: str
    ) -> ChatInviteLink:
        return ChatInviteLink.de_json(await self.client.request("revokeChatInviteLink", {
            "chat_id": chat_id, "invite_link": invite_link,
        }))  # type: ignore[return-value]

    async def approve_chat_join_request(self, chat_id: Union[int, str], user_id: int) -> bool:
        return await self.client.request("approveChatJoinRequest", {
            "chat_id": chat_id, "user_id": user_id,
        })

    async def decline_chat_join_request(self, chat_id: Union[int, str], user_id: int) -> bool:
        return await self.client.request("declineChatJoinRequest", {
            "chat_id": chat_id, "user_id": user_id,
        })

    # ==================================================================
    # Bot appearance
    # ==================================================================
    async def set_my_commands(
        self, commands: Sequence[Any], language_code: Optional[str] = None
    ) -> bool:
        normalized = [cmd.to_dict() for cmd in BotCommand.de_list(list(commands))]
        return await self.client.request("setMyCommands", {
            "commands": normalized, "language_code": language_code,
        })

    async def get_my_commands(self, language_code: Optional[str] = None) -> List[BotCommand]:
        result = await self.client.request("getMyCommands", {"language_code": language_code})
        return BotCommand.de_list(result)  # type: ignore[return-value]

    async def delete_my_commands(self, language_code: Optional[str] = None) -> bool:
        return await self.client.request("deleteMyCommands", {"language_code": language_code})

    async def set_my_name(self, name: Optional[str] = None, language_code: Optional[str] = None) -> bool:
        return await self.client.request("setMyName", {"name": name, "language_code": language_code})

    async def set_my_description(
        self, description: Optional[str] = None, language_code: Optional[str] = None
    ) -> bool:
        return await self.client.request("setMyDescription", {
            "description": description, "language_code": language_code,
        })

    async def set_my_short_description(
        self, short_description: Optional[str] = None, language_code: Optional[str] = None
    ) -> bool:
        return await self.client.request("setMyShortDescription", {
            "short_description": short_description, "language_code": language_code,
        })

    # ==================================================================
    # FSM
    # ==================================================================
    def set_state(self, user_id: int, state: Union[State, str, None], chat_id: int = 0) -> None:
        self.storage.set_state(user_id, chat_id, state_full_name(state))

    def get_state(self, user_id: int, chat_id: int = 0) -> Optional[str]:
        return self.storage.get_state(user_id, chat_id)

    def reset_state(self, user_id: int, chat_id: int = 0) -> None:
        self.storage.reset_state(user_id, chat_id)

    def get_state_data(self, user_id: int, chat_id: int = 0) -> Dict[str, Any]:
        return self.storage.get_data(user_id, chat_id)

    def update_state_data(self, user_id: int, chat_id: int = 0, **data: Any) -> Dict[str, Any]:
        return self.storage.update_data(user_id, chat_id, **data)

    def clear_state_data(self, user_id: int, chat_id: int = 0) -> None:
        self.storage.clear(user_id, chat_id)

    # ==================================================================
    # Middleware & error handling
    # ==================================================================
    def register_middleware(
        self, update_types: Optional[Sequence[str]] = None
    ) -> Any:
        """Decorator: register an **async** middleware (``await next_()``)."""
        manager = self.middleware

        def decorator(fn: Any) -> Any:
            return manager.register(fn, update_types)

        return decorator

    def exception_handler(self, fn: Any) -> Any:
        """Decorator: catch every exception raised by handlers/middleware."""
        self.router.exception_handler = fn
        return fn

    # ==================================================================
    # Update intake
    # ==================================================================
    async def process_new_updates(self, updates: Iterable[Union[Update, dict]]) -> int:
        """Feed webhook updates into the router (awaits async handlers)."""
        count = 0
        for update in updates:
            if isinstance(update, dict):
                update = Update.de_json(update)
            await self.router.process_update(update)
            count += 1
        return count

    async def process_webhook_update(self, update: Union[Update, dict]) -> None:
        """Process exactly one webhook payload — the FastAPI/aiohttp seam."""
        await self.process_new_updates([update])

    async def polling(
        self,
        interval: float = 0,
        long_polling_timeout: int = 10,
        allowed_updates: Optional[Iterable[str]] = None,
        stop_event: Optional[asyncio.Event] = None,
        retry_wait: float = 1.0,
        skip_pending: bool = False,
    ) -> None:
        """Async long-polling loop; pass an ``asyncio.Event`` as ``stop_event`` to stop it."""
        stop = stop_event or asyncio.Event()
        offset = 0

        if skip_pending:
            try:
                updates = await self.get_updates(offset=-1, timeout=0)
                if updates:
                    offset = updates[-1].update_id + 1
            except (ApiTelegramError, NetworkError) as exc:
                logger.warning("skip_pending probe failed: %s", exc)

        while not stop.is_set():
            try:
                updates = await self.get_updates(
                    offset=offset or None,
                    timeout=long_polling_timeout,
                    allowed_updates=allowed_updates,
                )
            except (ApiTelegramError, NetworkError) as exc:
                logger.error("getUpdates failed: %s — retrying in %.1fs", exc, retry_wait)
                await self._sleep_or_stop(stop, retry_wait)
                continue

            for update in updates:
                await self.router.process_update(update)
                offset = update.update_id + 1

            if interval:
                await self._sleep_or_stop(stop, interval)

    async def infinity_polling(
        self,
        interval: float = 0,
        long_polling_timeout: int = 10,
        allowed_updates: Optional[Iterable[str]] = None,
        max_backoff: float = 60.0,
        skip_pending: bool = False,
    ) -> None:
        backoff = 1.0
        while True:
            try:
                await self.polling(
                    interval=interval,
                    long_polling_timeout=long_polling_timeout,
                    allowed_updates=allowed_updates,
                    skip_pending=skip_pending,
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - restart is the whole point
                logger.error("Polling crashed: %s — restarting in %.0fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    @staticmethod
    async def _sleep_or_stop(stop: asyncio.Event, delay: float) -> None:
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass
