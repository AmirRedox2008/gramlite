"""Exception hierarchy of GramLite.

The hierarchy is intentionally small and predictable::

    TelegramError                     base of everything
    ├── NetworkError                  request never reached Telegram
    ├── ApiHTTPError                  non-JSON HTTP answer (502 HTML page, ...)
    └── ApiTelegramError              Telegram answered {"ok": false, ...}
        ├── BotBlockedError           403 — user blocked the bot
        ├── InvalidTokenError         401/404 — token revoked or wrong
        └── RateLimitError            429 — carries ``retry_after``

Catching :class:`TelegramError` always catches everything the library raises;
catching :class:`ApiTelegramError` covers every API-level rejection.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "ApiHTTPError",
    "ApiTelegramError",
    "BotBlockedError",
    "InvalidTokenError",
    "NetworkError",
    "RateLimitError",
    "TelegramError",
]


class TelegramError(Exception):
    """Base class for all errors raised by GramLite."""


class NetworkError(TelegramError):
    """A network-level failure occurred while calling the Bot API."""


class ApiHTTPError(TelegramError):
    """The API endpoint returned a non-JSON HTTP response."""

    def __init__(self, status_code: int, method_name: str) -> None:
        self.status_code = status_code
        self.method_name = method_name
        super().__init__(f"HTTP {status_code} while calling {method_name!r}")


class ApiTelegramError(TelegramError):
    """Telegram returned ``{"ok": false, ...}`` for an API call."""

    def __init__(
        self,
        method_name: str,
        error_code: int,
        description: str,
        result_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.method_name = method_name
        self.error_code = error_code
        self.description = description
        self.result_json = result_json or {}
        super().__init__(f"[{error_code}] {method_name}: {description}")

    @property
    def retry_after(self) -> Optional[int]:
        """Seconds to wait when the error is a ``429 Too Many Requests``."""
        parameters = self.result_json.get("parameters") or {}
        return parameters.get("retry_after")


class BotBlockedError(ApiTelegramError):
    """HTTP 403 — the target user blocked the bot (or is not reachable)."""


class InvalidTokenError(ApiTelegramError):
    """HTTP 401/404 — the bot token is wrong, revoked or malformed."""


class RateLimitError(ApiTelegramError):
    """HTTP 429 — too many requests. Honor :attr:`retry_after` before retrying."""
