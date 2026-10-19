"""Tests for the polling loop: offset bookkeeping, resilience, skip_pending."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from gramlite.exceptions import NetworkError
from gramlite.polling import run_infinity_polling, run_polling
from gramlite.types import Update

from conftest import UPDATE_JSON


def _registry_capturing(received):
    from gramlite.handlers import HandlerRegistry
    registry = HandlerRegistry()
    registry.add("message", lambda m: received.append(m), func=lambda m: True)
    return registry


def _fake_bot(pages, stop=None):
    """Duck-typed bot stub: pops one page of raw updates per get_updates call."""
    calls = []

    def get_updates(offset=None, limit=None, timeout=None, allowed_updates=None):
        calls.append(offset)
        page = pages.pop(0) if pages else []
        if stop is not None and len(calls) >= 2:
            stop.set()
        return Update.de_list(page)

    return SimpleNamespace(get_updates=get_updates), calls


class FakeStop:
    """Duck-typed threading.Event that never sleeps for real."""

    def __init__(self):
        self._set = False
        self.waits = []

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self._set


def test_offset_advances_between_cycles():
    stop = threading.Event()
    received = []
    pages = [
        [dict(UPDATE_JSON)],
        [{"update_id": 101, "message": dict(UPDATE_JSON["message"])}],
    ]
    bot, calls = _fake_bot(pages, stop=stop)

    run_polling(bot, _registry_capturing(received), stop_event=stop, long_polling_timeout=0)

    assert calls == [None, 101]
    assert len(received) == 2


def test_api_errors_are_survived():
    stop = threading.Event()
    received = []
    calls = []

    def flaky_get_updates(offset=None, limit=None, timeout=None, allowed_updates=None):
        calls.append(offset)
        if len(calls) == 1:
            raise NetworkError("connection reset")
        stop.set()
        return []

    bot = SimpleNamespace(get_updates=flaky_get_updates)
    run_polling(bot, _registry_capturing(received), stop_event=stop,
                long_polling_timeout=0, retry_wait=0.01)

    assert len(calls) == 2  # failed once, then retried and stopped cleanly
    assert received == []


def test_skip_pending_resumes_after_last_update():
    stop = threading.Event()
    pages = [[{"update_id": 500, "message": dict(UPDATE_JSON["message"])}], []]
    bot, calls = _fake_bot(pages, stop=stop)

    run_polling(bot, _registry_capturing([]), stop_event=stop,
                long_polling_timeout=0, skip_pending=True)

    assert calls[0] == -1   # probe: fetch only the last update
    assert calls[1] == 501  # resume strictly after it


def test_infinity_polling_restarts_after_crash():
    stop = FakeStop()
    received = []
    attempts = {"n": 0}

    class FakeBot:
        def get_updates(self, offset=None, limit=None, timeout=None, allowed_updates=None):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("fatal bug in parsing")
            stop.set()
            return []

    run_infinity_polling(FakeBot(), _registry_capturing(received), stop_event=stop)

    assert attempts["n"] >= 2            # crashed once, restarted, then exited
    assert stop.waits and stop.waits[0] == 1.0  # exponential back-off started at 1s
