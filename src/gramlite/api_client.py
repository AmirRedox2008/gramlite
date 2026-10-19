"""HTTP transport layer shared by the synchronous client.

The client is deliberately thin: it knows how to

1. build the endpoint URL (``.../bot<token>/<method>``),
2. serialise request parameters (including ``TelegramObject`` markup),
3. retry ``429`` / ``5xx`` responses with a sane back-off policy,
4. translate every failure mode into a typed exception.

A ``requests.Session`` can be injected, which gives us connection pooling in
production and painless mocking in tests.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import requests

from .exceptions import (
    ApiHTTPError,
    ApiTelegramError,
    BotBlockedError,
    InvalidTokenError,
    NetworkError,
    RateLimitError,
    TelegramError,
)
from .types import TelegramObject

logger = logging.getLogger("gramlite.client")

__all__ = ["APIClient", "prepare_params"]


def _api_error(method_name: str, data: dict, status_code: int) -> ApiTelegramError:
    """Translate an ``{"ok": false}`` payload into the most specific exception."""
    error_code = int(data.get("error_code") or status_code or 0)
    description = data.get("description", "No description provided")
    cls = ApiTelegramError
    if error_code == 403:
        cls = BotBlockedError
    elif error_code in (401, 404):
        cls = InvalidTokenError
    elif error_code == 429:
        cls = RateLimitError
    return cls(
        method_name=method_name,
        error_code=error_code,
        description=description,
        result_json=data,
    )


def prepare_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise a parameter dict before sending it to Telegram.

    * ``None`` values are dropped (Telegram only wants present fields),
    * ``TelegramObject`` values (e.g. ``InlineKeyboardMarkup``) are serialised
      to their JSON representation, exactly as the Bot API expects for
      ``reply_markup``,
    * lists/dicts (poll options, bot commands, media albums, entities...) are
      JSON-encoded, because multipart/form fields must arrive as strings.
    """
    prepared: Dict[str, Any] = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, TelegramObject):
            value = json.dumps(value.to_dict(), ensure_ascii=False)
        elif isinstance(value, (list, dict, tuple)):
            value = json.dumps(value, ensure_ascii=False, default=_json_default)
        prepared[key] = value
    return prepared


def _json_default(obj: Any) -> Any:
    if isinstance(obj, TelegramObject):
        return obj.to_dict()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


class APIClient:
    """Synchronous low-level client for the Telegram Bot API."""

    DEFAULT_BASE_URL = "https://api.telegram.org"

    def __init__(
        self,
        token: str,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not token:
            raise ValueError("A bot token is required (get one from @BotFather).")
        self.token = token
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        # Session injection keeps the class testable and enables pooling.
        self.session = session or requests.Session()

    # ------------------------------------------------------------------ urls
    @property
    def api_url(self) -> str:
        return f"{self.base_url}/bot{self.token}"

    def file_download_url(self, file_path: str) -> str:
        """Public URL from which a file downloaded via ``getFile`` can be fetched."""
        return f"{self.base_url}/file/bot{self.token}/{file_path}"

    # --------------------------------------------------------------- request
    def request(
        self,
        method_name: str,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Call a Bot API method and return the parsed ``result`` payload.

        Raises :class:`ApiTelegramError` when Telegram answers ``ok: false``
        and :class:`NetworkError` when the request never reaches Telegram.
        """
        url = f"{self.api_url}/{method_name}"
        payload = prepare_params(params)
        attempt = 0

        while True:
            try:
                response = self.session.post(
                    url, data=payload, files=files, timeout=timeout or self.timeout
                )
            except requests.RequestException as exc:
                raise NetworkError(f"Network failure while calling {method_name}: {exc}") from exc

            if self._should_retry(response.status_code) and attempt < self.max_retries:
                delay = self._retry_delay(response, attempt)
                logger.warning(
                    "HTTP %s from %s — retrying in %.1fs (attempt %d/%d)",
                    response.status_code, method_name, delay, attempt + 1, self.max_retries,
                )
                attempt += 1
                time.sleep(delay)
                continue

            return self._parse(method_name, response)

    # ------------------------------------------------------------ files
    def get_bytes(self, url: str, timeout: Optional[float] = None) -> bytes:
        """Download a raw file (e.g. from :meth:`file_download_url`)."""
        try:
            response = self.session.get(url, timeout=timeout or self.timeout)
        except requests.RequestException as exc:
            raise NetworkError(f"Network failure while downloading file: {exc}") from exc
        if response.status_code != 200:
            raise ApiHTTPError(response.status_code, "file download")
        return response.content

    # ------------------------------------------------------------ internals
    @staticmethod
    def _should_retry(status_code: int) -> bool:
        # 429 = rate limited, 5xx = Telegram/server-side hiccups.
        return status_code == 429 or status_code >= 500

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        """Honour Telegram's ``retry_after`` when present, else back off exponentially."""
        try:
            data = response.json()
            retry_after = (data.get("parameters") or {}).get("retry_after")
            if retry_after:
                return float(retry_after)
        except ValueError:
            pass
        return self.backoff_factor * (2 ** attempt)

    @staticmethod
    def _parse(method_name: str, response: requests.Response) -> Any:
        try:
            data = response.json()
        except ValueError:
            if response.status_code != 200:
                raise ApiHTTPError(response.status_code, method_name)
            raise TelegramError(f"Malformed (non-JSON) response from {method_name}")

        if data.get("ok"):
            return data.get("result")

        raise _api_error(method_name, data, response.status_code)
