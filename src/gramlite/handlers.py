"""Update routing: handler registration, filters and the dispatcher.

The routing model follows the "first match wins" rule made popular by
pyTelegramBotAPI: handlers are checked in registration order and the first
one whose filters all pass is executed; remaining handlers are skipped.

Filters available on message handlers
-------------------------------------
===================  =======================================================
filter               meaning
===================  =======================================================
``commands``         message starts with one of the given ``/commands``
``content_types``    message payload type (``text``, ``photo``, ... or ``all``)
``regexp``           ``re.search`` against the message text (callback data
                     for callback handlers, query text for inline handlers)
``chat_types``       chat type (``private``, ``group``, ``supergroup``, ``channel``)
``state``            FSM state (a :class:`~gramlite.fsm.State`, its string
                     name, ``"*"`` for any state) — see :mod:`gramlite.fsm`
``func``             any callable receiving the payload and returning truthy
``custom_filter``    a :class:`BaseFilter` subclass instance for reusable,
                     self-written filters
``pass_args``        pass the command's trailing arguments to the handler
===================  =======================================================

All given filters are combined with a logical AND.

Resilience rules (documented in ``ARCHITECTURE.md``):

* exceptions raised inside a filter check are logged and the handler skipped;
* exceptions raised inside a handler go to the registered exception handler
  (``bot.register_exception_handler``) or, if none is registered, are logged —
  one broken handler can never kill the polling loop.
"""

from __future__ import annotations

import inspect
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Pattern, Sequence, Tuple, Union

from .types import Message, Update

logger = logging.getLogger("gramlite.handlers")

__all__ = [
    "CONTENT_TYPES", "AsyncHandlerRegistry", "BaseFilter", "Handler",
    "HandlerRegistry", "HandlerRegistrationMixin",
]

#: Payload fields an :class:`~gramlite.types.Update` can carry, in routing order.
UPDATE_PAYLOADS: Tuple[str, ...] = (
    "message", "edited_message", "channel_post", "edited_channel_post",
    "callback_query", "inline_query", "pre_checkout_query", "poll",
    "poll_answer", "my_chat_member", "chat_member", "chat_join_request",
)

#: Content types recognised by :attr:`Message.content_type`.
CONTENT_TYPES: Tuple[str, ...] = (
    "text", "audio", "document", "animation", "photo", "sticker", "video",
    "video_note", "voice", "location", "venue", "contact", "poll", "dice",
    "invoice", "successful_payment",
    "new_chat_members", "left_chat_member", "new_chat_title", "pinned_message",
)

#: Valid chat types for the ``chat_types`` filter.
CHAT_TYPES: Tuple[str, ...] = ("private", "group", "supergroup", "channel")


class BaseFilter:
    """Base class for user-defined, reusable filters.

    Subclass it and implement :meth:`check`; instances are passed to handlers
    via ``custom_filter=``::

        class AdminFilter(BaseFilter):
            def check(self, message) -> bool:
                return message.from_user.id in ADMINS

        @bot.message_handler(custom_filter=AdminFilter())
        def admin_panel(message): ...

    Multiple ``custom_filter`` values (a list/tuple) are combined with AND.
    """

    name: str = "BaseFilter"

    def check(self, payload: Any) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def __call__(self, payload: Any) -> bool:
        return self.check(payload)


class Handler:
    """One registered handler: a callback plus the filters guarding it."""

    __slots__ = (
        "callback", "update_type", "commands", "regexp", "content_types",
        "chat_types", "func", "custom_filters", "state", "pass_args",
    )

    def __init__(
        self,
        callback: Callable[..., Any],
        update_type: str = "message",
        *,
        commands: Optional[Sequence[str]] = None,
        regexp: Optional[Union[str, Pattern[str]]] = None,
        content_types: Optional[Sequence[str]] = None,
        chat_types: Optional[Sequence[str]] = None,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
        state: Optional[Any] = None,
        pass_args: bool = False,
    ) -> None:
        self.callback = callback
        self.update_type = update_type
        self.commands = [cmd.lower().lstrip("/") for cmd in commands] if commands else None
        self.regexp = re.compile(regexp) if isinstance(regexp, str) else regexp
        self.content_types = tuple(content_types) if content_types else ("text",)
        self.chat_types = tuple(chat_types) if chat_types else None
        self.func = func
        if custom_filter is None:
            self.custom_filters: Tuple[BaseFilter, ...] = ()
        elif isinstance(custom_filter, (list, tuple)):
            self.custom_filters = tuple(custom_filter)
        else:
            self.custom_filters = (custom_filter,)
        self.state = state
        self.pass_args = pass_args

    # ------------------------------------------------------------------
    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(self.callback)

    def check(self, payload: Any, registry: Optional["HandlerRegistry"] = None) -> bool:
        """Return True when every filter passes for ``payload``."""
        if isinstance(payload, Message):
            return self._check_message(payload, registry)
        # CallbackQuery / InlineQuery / every other payload kind.
        if self.regexp is not None:
            subject = (
                getattr(payload, "data", None)
                or getattr(payload, "query", None)
            )
            if not isinstance(subject, str) or not self.regexp.search(subject):
                return False
        for custom in self.custom_filters:
            if not custom.check(payload):
                return False
        if self.func is not None and not self.func(payload):
            return False
        return True

    def _check_message(self, message: Message, registry: Optional["HandlerRegistry"]) -> bool:
        if "all" not in self.content_types and message.content_type not in self.content_types:
            return False
        if self.commands is not None and not self._match_commands(message, registry):
            return False
        if self.regexp is not None:
            if not message.text or not self.regexp.search(message.text):
                return False
        if self.chat_types is not None and getattr(message.chat, "type", None) not in self.chat_types:
            return False
        for custom in self.custom_filters:
            if not custom.check(message):
                return False
        if self.func is not None and not self.func(message):
            return False
        return True

    def _match_commands(self, message: Message, registry: Optional["HandlerRegistry"]) -> bool:
        command = message.extract_command()
        if command is None or self.commands is None:
            return False
        # Respect the @botname suffix: /start@other_bot must NOT match us.
        raw_first = (message.text or "").split(maxsplit=1)[0]
        if "@" in raw_first and registry is not None and registry.bot_username:
            mentioned = raw_first.split("@", 1)[1].lower()
            if mentioned and mentioned != registry.bot_username.lower():
                return False
        return command in self.commands

    def extract_args(self, message: Message) -> List[str]:
        """Trailing arguments of a command message (``/ban 42 spam`` → ``["42", "spam"]``)."""
        text = (message.text or "").strip()
        if not text:
            return []
        parts = text.split(maxsplit=1)
        return parts[1].split() if len(parts) > 1 else []

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<Handler {self.update_type} {self.callback.__name__!r}>"


class HandlerRegistry:
    """Stores handlers per update type and dispatches updates to them.

    The sync registry calls callbacks directly. The async twin
    (:class:`AsyncHandlerRegistry`) awaits coroutine callbacks — and awaits
    async middleware — so ``async def`` handlers genuinely run.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Handler]] = {key: [] for key in UPDATE_PAYLOADS}
        #: Set by the owning Bot: used for ``/command@botname`` matching.
        self.bot_username: Optional[str] = None
        #: Callable ``(payload, exception) -> None`` or None.
        self.exception_handler: Optional[Callable[[Any, Exception], Any]] = None
        #: Middleware manager owned by the Bot (sync or async flavour).
        self.middleware: Any = None

    # ------------------------------------------------------------------
    def register(self, handler: Handler) -> Callable[..., Any]:
        self._handlers[handler.update_type].append(handler)
        return handler.callback

    def add(self, update_type: str, callback: Callable[..., Any], **filters: Any) -> Callable[..., Any]:
        return self.register(Handler(callback, update_type, **filters))

    # ------------------------------------------------------------------
    def process_update(self, update: Update) -> bool:
        """Dispatch one update. Returns True when a matching handler ran."""
        for update_type in UPDATE_PAYLOADS:
            payload = getattr(update, update_type, None)
            if payload is None:
                continue
            final = lambda p, _t=update_type: self._execute(_t, p)  # noqa: E731
            chain = self.middleware.wrap(update_type, final) if self.middleware is not None else final
            try:
                result = chain(payload)
            except Exception as exc:  # middleware errors are handler-grade errors
                self._handle_exception(update_type, payload, exc)
                result = True
            return bool(result)
        return False

    # -------------------------------------------------------- internals
    def _execute(self, update_type: str, payload: Any) -> bool:
        """Find the first matching handler and run it. Returns True on match."""
        for handler in self._handlers[update_type]:
            try:
                matched = handler.check(payload, self)
            except Exception:
                logger.exception("Filter check crashed on %r — skipping", handler.callback)
                continue
            if not matched:
                continue
            self._run_callback(handler, payload, update_type)
            return True
        return False

    def _run_callback(self, handler: Handler, payload: Any, update_type: str) -> None:
        try:
            if handler.pass_args and isinstance(payload, Message):
                handler.callback(payload, *handler.extract_args(payload))
            else:
                handler.callback(payload)
        except Exception as exc:
            self._handle_exception(update_type, payload, exc, handler=handler)

    def _handle_exception(
        self,
        update_type: str,
        payload: Any,
        exc: Exception,
        handler: Optional[Handler] = None,
    ) -> None:
        if self.exception_handler is not None:
            try:
                self.exception_handler(payload, exc)
                return
            except Exception:
                logger.exception("Exception handler itself crashed")
        if handler is not None:
            logger.exception("Handler %r raised inside %s", handler.callback, update_type)
        else:
            logger.exception("Dispatch raised inside %s: %s", update_type, exc)

    def clear(self) -> None:
        for bucket in self._handlers.values():
            bucket.clear()


class AsyncHandlerRegistry(HandlerRegistry):
    """Async twin of :class:`HandlerRegistry`.

    ``process_update`` is a coroutine; ``async def`` handlers are awaited,
    plain functions are called directly.
    """

    async def process_update(self, update: Update) -> bool:
        for update_type in UPDATE_PAYLOADS:
            payload = getattr(update, update_type, None)
            if payload is None:
                continue
            final = lambda p, _t=update_type: self._execute(_t, p)  # noqa: E731
            chain = self.middleware.wrap(update_type, final) if self.middleware is not None else final
            try:
                result = await chain(payload)
            except Exception as exc:
                self._handle_exception(update_type, payload, exc)
                result = True
            return bool(result)
        return False

    async def _execute(self, update_type: str, payload: Any) -> bool:
        for handler in self._handlers[update_type]:
            try:
                matched = handler.check(payload, self)
            except Exception:
                logger.exception("Filter check crashed on %r — skipping", handler.callback)
                continue
            if not matched:
                continue
            await self._run_callback(handler, payload, update_type)
            return True
        return False

    async def _run_callback(self, handler: Handler, payload: Any, update_type: str) -> None:
        try:
            if handler.pass_args and isinstance(payload, Message):
                result = handler.callback(payload, *handler.extract_args(payload))
            else:
                result = handler.callback(payload)
            if inspect.iscoroutine(result):
                await result
        except Exception as exc:
            self._handle_exception(update_type, payload, exc, handler=handler)


class HandlerRegistrationMixin:
    """Decorator helpers shared by the sync and async bots."""

    #: Set by the concrete Bot class (HandlerRegistry instance).
    router: HandlerRegistry

    # ------------------------------------------------------------ internal
    def _register_handler(
        self,
        update_type: str,
        callback: Callable[..., Any],
        *,
        commands: Optional[Sequence[str]] = None,
        regexp: Optional[Union[str, Pattern[str]]] = None,
        content_types: Optional[Sequence[str]] = None,
        chat_types: Optional[Sequence[str]] = None,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
        state: Optional[Any] = None,
        pass_args: bool = False,
    ) -> Callable[..., Any]:
        if state is not None:
            from .fsm import StateFilter  # local import avoids a cycle

            custom_filter = _merge_filters(custom_filter, StateFilter(self, state))
        self.router.register(
            Handler(
                callback, update_type,
                commands=commands, regexp=regexp, content_types=content_types,
                chat_types=chat_types, func=func, custom_filter=custom_filter,
                pass_args=pass_args,
            )
        )
        return callback

    # ------------------------------------------------------------- message
    def message_handler(
        self,
        commands: Optional[Sequence[str]] = None,
        regexp: Optional[Union[str, Pattern[str]]] = None,
        content_types: Optional[Sequence[str]] = None,
        chat_types: Optional[Sequence[str]] = None,
        func: Optional[Callable[[Message], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
        state: Optional[Any] = None,
        pass_args: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a handler for new messages.

        Decorators can be stacked so one function serves several conditions::

            @bot.message_handler(commands=["hello"])
            @bot.message_handler(func=lambda m: "👋" in (m.text or ""))
            def hi(message): ...
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler(
                "message", fn, commands=commands, regexp=regexp,
                content_types=content_types, chat_types=chat_types,
                func=func, custom_filter=custom_filter, state=state,
                pass_args=pass_args,
            )

        return decorator

    def edited_message_handler(self, **filters: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("edited_message", fn, **filters)

        return decorator

    def channel_post_handler(self, **filters: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("channel_post", fn, **filters)

        return decorator

    def edited_channel_post_handler(self, **filters: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("edited_channel_post", fn, **filters)

        return decorator

    # ------------------------------------------------------------ callbacks
    def callback_query_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        regexp: Optional[Union[str, Pattern[str]]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a handler for inline-keyboard callback presses.

        ``regexp`` is matched against ``callback_query.data`` — handy for
        namespaced buttons like ``page:2``.
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler(
                "callback_query", fn, func=func, regexp=regexp, custom_filter=custom_filter,
            )

        return decorator

    # ---------------------------------------------------------- inline mode
    def inline_query_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        regexp: Optional[Union[str, Pattern[str]]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a handler for inline queries (``@yourbot query text``)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler(
                "inline_query", fn, func=func, regexp=regexp, custom_filter=custom_filter,
            )

        return decorator

    # -------------------------------------------------------------- payments
    def pre_checkout_query_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a handler for payment pre-checkout queries (answer within 10s!)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("pre_checkout_query", fn, func=func, custom_filter=custom_filter)

        return decorator

    # ----------------------------------------------------------------- polls
    def poll_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("poll", fn, func=func, custom_filter=custom_filter)

        return decorator

    def poll_answer_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("poll_answer", fn, func=func, custom_filter=custom_filter)

        return decorator

    # ------------------------------------------------------- member updates
    def my_chat_member_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Fires when the bot's own status in a chat changes (kicked, promoted...)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("my_chat_member", fn, func=func, custom_filter=custom_filter)

        return decorator

    def chat_member_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Fires when any member's status changes (requires ``chat_member`` in
        ``allowed_updates`` when polling)."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("chat_member", fn, func=func, custom_filter=custom_filter)

        return decorator

    def chat_join_request_handler(
        self,
        func: Optional[Callable[[Any], bool]] = None,
        custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Fires for each pending join request to the chat."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return self._register_handler("chat_join_request", fn, func=func, custom_filter=custom_filter)

        return decorator


def _merge_filters(
    custom_filter: Optional[Union[BaseFilter, Sequence[BaseFilter]]],
    extra: BaseFilter,
) -> Union[BaseFilter, Sequence[BaseFilter]]:
    if custom_filter is None:
        return extra
    if isinstance(custom_filter, (list, tuple)):
        return [extra, *custom_filter]
    return [extra, custom_filter]
