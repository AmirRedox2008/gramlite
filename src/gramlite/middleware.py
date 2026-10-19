"""Middleware — code that runs *around* every handler dispatch.

Middlewares form a chain-of-responsibility per update type. Each middleware
receives the payload and a ``next()`` callable; calling ``next()`` continues
the chain (eventually reaching the matching handler). *Not* calling ``next()``
short-circuits the dispatch — useful for auth gates, rate limiting, logging
or muting specific chats.

Sync bots::

    @bot.middleware(update_type="message")
    def log_all(message, next_):
        logger.info("Message from %s", message.from_user.id)
        next_()                       # continue → handler runs

Async bots (note the ``await``)::

    @bot.middleware(update_type="message")
    async def gate(message, next_):
        if banned(message.from_user.id):
            return                    # short-circuit: handler never runs
        await next_()

``update_type=None`` (the default) runs the middleware for *every* payload
kind. Middleware exceptions are handled exactly like handler exceptions:
routed to the registered exception handler, or logged.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple

__all__ = ["AsyncMiddlewareManager", "MiddlewareManager"]


class MiddlewareManager:
    """Sync middleware chain (used by :class:`~gramlite.bot.Bot`)."""

    def __init__(self) -> None:
        self._middlewares: List[Tuple[Callable[..., Any], Optional[Tuple[str, ...]]]] = []

    def register(
        self,
        fn: Callable[[Any, Callable[[], Any]], Any],
        update_types: Optional[Sequence[str]] = None,
    ) -> Callable[[Any, Callable[[], Any]], Any]:
        """Register a middleware function; returns the function (decorator-friendly)."""
        types = tuple(update_types) if update_types else None
        self._middlewares.append((fn, types))
        return fn

    def wrap(self, update_type: str, final: Callable[[Any], Any]) -> Callable[[Any], Any]:
        """Return a callable that runs ``final`` inside the middleware chain."""
        chain = [fn for fn, types in self._middlewares if types is None or update_type in types]
        if not chain:
            return final

        def run(payload: Any) -> Any:
            return self._invoke(chain, 0, payload, final)

        return run

    @staticmethod
    def _invoke(
        chain: List[Callable[..., Any]],
        index: int,
        payload: Any,
        final: Callable[[Any], Any],
    ) -> Any:
        if index >= len(chain):
            return final(payload)
        return chain[index](payload, lambda: MiddlewareManager._invoke(chain, index + 1, payload, final))


class AsyncMiddlewareManager:
    """Async middleware chain (used by :class:`~gramlite.async_bot.AsyncBot`).

    Middleware functions must be coroutine functions and ``await next_()``.
    """

    def __init__(self) -> None:
        self._middlewares: List[Tuple[Callable[..., Any], Optional[Tuple[str, ...]]]] = []

    def register(
        self,
        fn: Callable[..., Any],
        update_types: Optional[Sequence[str]] = None,
    ) -> Callable[..., Any]:
        types = tuple(update_types) if update_types else None
        self._middlewares.append((fn, types))
        return fn

    def wrap(self, update_type: str, final: Callable[..., Any]) -> Callable[..., Any]:
        """Return an *async* callable that awaits ``final`` inside the chain."""
        chain = [fn for fn, types in self._middlewares if types is None or update_type in types]
        if not chain:
            return final

        async def run(payload: Any) -> Any:
            return await AsyncMiddlewareManager._invoke(chain, 0, payload, final)

        return run

    @staticmethod
    async def _invoke(
        chain: List[Callable[..., Any]],
        index: int,
        payload: Any,
        final: Callable[..., Any],
    ) -> Any:
        if index >= len(chain):
            return await final(payload)
        return await chain[index](payload, AsyncMiddlewareManager._make_next(chain, index + 1, payload, final))

    @staticmethod
    def _make_next(
        chain: List[Callable[..., Any]],
        index: int,
        payload: Any,
        final: Callable[..., Any],
    ) -> Callable[[], Any]:
        async def next_() -> Any:
            return await AsyncMiddlewareManager._invoke(chain, index, payload, final)

        return next_
