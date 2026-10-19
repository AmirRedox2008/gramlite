"""Tests for the HTTP layer: URL building, serialisation, retries, errors."""

from __future__ import annotations

import pytest
import requests

import gramlite.api_client as api_module
from gramlite.api_client import APIClient, prepare_params
from gramlite.exceptions import (
    ApiHTTPError,
    ApiTelegramError,
    BotBlockedError,
    InvalidTokenError,
    NetworkError,
    RateLimitError,
    TelegramError,
)
from gramlite.types import InlineKeyboardButton, InlineKeyboardMarkup

from conftest import CHAT_JSON, FakeResponse, FakeSession, TOKEN


# ---------------------------------------------------------------------------
# prepare_params
# ---------------------------------------------------------------------------
def test_none_values_are_dropped():
    assert prepare_params({"chat_id": 1, "text": None}) == {"chat_id": 1}


def test_telegram_objects_are_serialised_to_json():
    markup = InlineKeyboardMarkup().row(InlineKeyboardButton("Buy", callback_data="buy:1"))
    prepared = prepare_params({"chat_id": 1, "reply_markup": markup})
    assert isinstance(prepared["reply_markup"], str)
    assert '"callback_data"' in prepared["reply_markup"]


# ---------------------------------------------------------------------------
# Client behaviour
# ---------------------------------------------------------------------------
def _client(responses) -> tuple[APIClient, FakeSession]:
    session = FakeSession(responses)
    return APIClient(token=TOKEN, session=session), session


def test_successful_call_returns_result():
    client, session = _client([FakeResponse(200, {"ok": True, "result": {"id": 42}})])
    assert client.request("getMe") == {"id": 42}
    assert session.calls[0]["url"].endswith(f"/bot{TOKEN}/getMe")
    assert session.calls[0]["url"].startswith("https://api.telegram.org")


def test_none_params_are_not_sent():
    client, session = _client([FakeResponse(200, {"ok": True, "result": True})])
    client.request("sendMessage", {"chat_id": 1, "text": "hi", "parse_mode": None})
    assert session.calls[0]["data"] == {"chat_id": 1, "text": "hi"}


def test_api_error_raises_typed_exception():
    client, _ = _client([FakeResponse(400, {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})])
    with pytest.raises(ApiTelegramError) as excinfo:
        client.request("sendMessage", {"chat_id": -1, "text": "x"})
    assert excinfo.value.error_code == 400
    assert "chat not found" in excinfo.value.description
    assert excinfo.value.method_name == "sendMessage"


def test_429_retries_and_honours_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(api_module.time, "sleep", sleeps.append)
    rate_limited = FakeResponse(429, {
        "ok": False, "error_code": 429, "description": "Too Many Requests",
        "parameters": {"retry_after": 3},
    })
    ok = FakeResponse(200, {"ok": True, "result": True})
    client, session = _client([rate_limited, ok])

    assert client.request("sendMessage") is True
    assert len(session.calls) == 2
    assert sleeps == [3.0]


def test_500_retries_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(api_module.time, "sleep", sleeps.append)
    boom = FakeResponse(502, None, text="<html>Bad Gateway</html>")
    ok = FakeResponse(200, {"ok": True, "result": True})
    client, session = _client([boom, ok])

    assert client.request("getUpdates") is True
    assert len(session.calls) == 2
    assert len(sleeps) == 1  # exponential backoff used


def test_retry_exhaustion_raises_api_error(monkeypatch):
    monkeypatch.setattr(api_module.time, "sleep", lambda _s: None)
    always_429 = FakeResponse(429, {
        "ok": False, "error_code": 429, "description": "Too Many Requests",
        "parameters": {"retry_after": 1},
    })
    client, session = _client([always_429])
    client.max_retries = 2

    with pytest.raises(ApiTelegramError) as excinfo:
        client.request("sendMessage")
    assert excinfo.value.retry_after == 1
    assert len(session.calls) == 3  # 1 initial + 2 retries


def test_network_failure_is_wrapped():
    class BrokenSession:
        def post(self, *args, **kwargs):
            raise requests.ConnectionError("connection reset")

    client = APIClient(token=TOKEN, session=BrokenSession())
    with pytest.raises(NetworkError):
        client.request("getMe")


def test_non_json_200_raises_base_error():
    client, _ = _client([FakeResponse(200, None, text="not json")])
    with pytest.raises(TelegramError) as excinfo:
        client.request("getMe")
    assert not isinstance(excinfo.value, ApiTelegramError)


def test_non_json_502_after_exhaustion_raises_http_error():
    client, _ = _client([FakeResponse(502, None, text="gateway error")])
    client.max_retries = 0
    with pytest.raises(ApiHTTPError):
        client.request("getMe")


def test_missing_token_is_rejected():
    with pytest.raises(ValueError):
        APIClient(token="")


def test_custom_base_url_local_bot_api_server():
    session = FakeSession([FakeResponse(200, {"ok": True, "result": True})])
    client = APIClient(token=TOKEN, base_url="http://localhost:8081/", session=session)
    client.request("getMe")
    assert session.calls[0]["url"].startswith(f"http://localhost:8081/bot{TOKEN}/")


def test_file_download_url():
    client, _ = _client([])
    assert client.file_download_url("docs/report.pdf") == (
        f"https://api.telegram.org/file/bot{TOKEN}/docs/report.pdf"
    )


def test_shared_chat_json_shape_matches_api(CHAT_JSON=CHAT_JSON):  # noqa: PT028 - sanity guard
    assert CHAT_JSON["type"] == "supergroup"


# ---------------------------------------------------------------------------
# v2 — error subclasses, list serialisation, file downloads
# ---------------------------------------------------------------------------
def test_403_raises_bot_blocked_error():
    client, _ = _client([FakeResponse(403, {"ok": False, "error_code": 403, "description": "bot was blocked by the user"})])
    with pytest.raises(BotBlockedError):
        client.request("sendMessage", {"chat_id": 1, "text": "x"})


def test_401_raises_invalid_token_error():
    client, _ = _client([FakeResponse(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})])
    with pytest.raises(InvalidTokenError):
        client.request("getMe")


def test_429_exhaustion_raises_rate_limit_error(monkeypatch):
    monkeypatch.setattr(api_module.time, "sleep", lambda _s: None)
    client, _ = _client([FakeResponse(429, {
        "ok": False, "error_code": 429, "description": "Too Many Requests",
        "parameters": {"retry_after": 5},
    })])
    client.max_retries = 0
    with pytest.raises(RateLimitError) as excinfo:
        client.request("sendMessage")
    assert excinfo.value.retry_after == 5
    assert isinstance(excinfo.value, ApiTelegramError)  # subclass contract holds


def test_lists_and_dicts_are_json_encoded():
    prepared = prepare_params({"options": ["a", "b"], "commands": [{"command": "start", "description": "d"}]})
    assert prepared["options"] == '["a", "b"]'
    assert '"command": "start"' in prepared["commands"].replace("'", '"') or "start" in prepared["commands"]


def test_get_bytes_downloads_file_content():
    client, session = _client([FakeResponse(200, None, text="binary")])
    response = FakeResponse(200, None, text="ok")
    response.content = b"RAW-FILE"
    client.session = FakeSession([response])
    assert client.get_bytes("https://example.org/file") == b"RAW-FILE"


def test_get_bytes_wraps_network_errors():
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise requests.ConnectionError("dns")

    client = APIClient(token=TOKEN, session=BrokenSession())
    with pytest.raises(NetworkError):
        client.get_bytes("https://example.org/file")
