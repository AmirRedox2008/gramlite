"""Shared fixtures: sample payloads and fake transport doubles.

The whole suite runs offline — no real HTTP call is ever made. Two layers of
fakes are used:

* :class:`FakeSession` replaces ``requests.Session`` for :class:`APIClient`
  tests (full pipeline: params → retry → parse);
* :class:`RecordingClient` replaces ``APIClient`` for :class:`Bot` tests
  (method/params mapping and response parsing).
"""

from __future__ import annotations

import requests
import pytest

from gramlite.api_client import APIClient
from gramlite.bot import Bot
from gramlite.types import Update

TOKEN = "123456:TEST-TOKEN"

USER_JSON = {
    "id": 42,
    "is_bot": False,
    "first_name": "Ada",
    "last_name": "Lovelace",
    "username": "ada",
}
CHAT_JSON = {"id": -100123, "type": "supergroup", "title": "Test Group", "username": "testgroup"}
COMMAND_MESSAGE_JSON = {
    "message_id": 7,
    "from": USER_JSON,
    "chat": CHAT_JSON,
    "date": 1760000000,
    "text": "/start@mybot hello",
    "entities": [{"type": "bot_command", "offset": 0, "length": 13}],
}
PHOTO_MESSAGE_JSON = {
    "message_id": 8,
    "from": USER_JSON,
    "chat": {"id": 42, "type": "private", "first_name": "Ada"},
    "date": 1760000001,
    "photo": [
        {"file_id": "small_fid", "file_unique_id": "s1", "width": 90, "height": 90},
        {"file_id": "big_fid", "file_unique_id": "b1", "width": 800, "height": 800},
    ],
}
UPDATE_JSON = {"update_id": 100, "message": COMMAND_MESSAGE_JSON}
PHOTO_UPDATE_JSON = {"update_id": 102, "message": PHOTO_MESSAGE_JSON}
CALLBACK_UPDATE_JSON = {
    "update_id": 101,
    "callback_query": {
        "id": "cbq-1",
        "from": USER_JSON,
        "chat_instance": "-555",
        "data": "buy:3",
        "message": COMMAND_MESSAGE_JSON,
    },
}


class FakeResponse:
    """Stand-in for :class:`requests.Response`."""

    def __init__(self, status_code: int = 200, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or (str(json_data) if json_data is not None else "")

    def json(self):
        if self._json is None:
            raise ValueError("No JSON body")
        return self._json


class FakeSession:
    """Replaces ``requests.Session``; returns queued responses, records calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, data=None, files=None, timeout=None):
        self.calls.append({"url": url, "data": data, "files": files, "timeout": timeout})
        if len(self.responses) == 1:
            return self.responses[0]  # sticky single response (retry-exhaustion tests)
        return self.responses.pop(0)

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if len(self.responses) == 1:
            return self.responses[0]
        return self.responses.pop(0)


class RecordingClient:
    """Replaces :class:`APIClient` at the Bot level; returns a canned result.

    File payloads are consumed at call time (like a real upload would), so
    tests can assert on file contents even after the Bot closes the handle.
    """

    def __init__(self, result, token: str = TOKEN):
        self.token = token
        self.result = result
        self.calls = []

    def request(self, method_name, params=None, files=None, timeout=None):
        recorded_files = None
        if files:
            recorded_files = {}
            for key, value in files.items():
                if isinstance(value, tuple):
                    name, handle = value
                    content = handle.read() if hasattr(handle, "read") else handle
                    recorded_files[key] = (name, content)
                else:
                    recorded_files[key] = value
        self.calls.append({"method": method_name, "params": params, "files": recorded_files})
        return self.result

    def file_download_url(self, file_path):
        return f"https://api.telegram.org/file/bot{self.token}/{file_path}"


@pytest.fixture
def sample_update() -> Update:
    return Update.de_json(UPDATE_JSON)


@pytest.fixture
def photo_update() -> Update:
    return Update.de_json(PHOTO_UPDATE_JSON)


@pytest.fixture
def callback_update() -> Update:
    return Update.de_json(CALLBACK_UPDATE_JSON)


@pytest.fixture
def sample_message(sample_update):
    return sample_update.message


@pytest.fixture
def api_client():
    """An APIClient wired to a fake session; the session is exposed for asserts."""
    session = FakeSession([FakeResponse(200, {"ok": True, "result": True})])
    client = APIClient(token=TOKEN, session=session)
    client.session = session
    return client


@pytest.fixture
def recording_client():
    return RecordingClient(None)


@pytest.fixture
def bot(recording_client):
    return Bot(token=TOKEN, client=recording_client)


# ``requests`` import kept here so conftest documents the seam being faked.
_ = requests
