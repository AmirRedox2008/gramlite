"""Finite-state machine (FSM) for multi-step conversations.

Typical flow — a registration form::

    from gramlite.fsm import StateGroup, State, JSONFileStorage

    class Form(StateGroup):
        name = State()
        age = State()

    bot = Bot("TOKEN", storage=JSONFileStorage("states.json"))

    @bot.message_handler(commands=["form"])
    def start_form(message):
        bot.set_state(message.from_user.id, Form.name, message.chat.id)
        bot.reply_to(message, "What's your name?")

    @bot.message_handler(state=Form.name)
    def get_name(message):
        bot.update_state_data(message.from_user.id, name=message.text, chat_id=message.chat.id)
        bot.set_state(message.from_user.id, Form.age, message.chat.id)
        bot.reply_to(message, "How old are you?")

    @bot.message_handler(state=Form.age)
    def get_age(message):
        data = bot.get_state_data(message.from_user.id, message.chat.id)
        bot.reset_state(message.from_user.id, message.chat.id)
        bot.reply_to(message, f"Done: {data.get('name')}, {message.text}")

Handlers decorated with ``state=`` only fire while the user is in that state;
``state="*"`` matches any state. Handlers without a ``state`` filter always
run regardless of state.

Three storage backends are shipped:

* :class:`MemoryStorage` — fastest, lost on restart (default);
* :class:`JSONFileStorage` — survives restarts, zero infrastructure;
* :class:`RedisStorage` — for multi-process / multi-host deployments.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger("gramlite.fsm")

__all__ = [
    "BaseStorage", "JSONFileStorage", "MemoryStorage", "RedisStorage",
    "State", "StateFilter", "StateGroup", "state_full_name",
]


class State:
    """A single named state. Always defined inside a :class:`StateGroup`."""

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name
        self.group: Optional[str] = None

    @property
    def full_name(self) -> str:
        """``"GroupName:state_name"`` — the canonical string stored in backends."""
        if self.group and self.name:
            return f"{self.group}:{self.name}"
        return self.name or "unknown"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.full_name

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<State {self.full_name}>"


class StateGroup:
    """Groups related states. Subclass it and assign :class:`State` attributes::

        class Form(StateGroup):
            name = State()
            age = State()

    Names are auto-filled from the attribute names; ``Form.name.full_name``
    becomes ``"Form:name"``.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for attr_name, value in vars(cls).items():
            if isinstance(value, State):
                if value.name is None:
                    value.name = attr_name
                if value.group is None:
                    value.group = cls.__name__


def state_full_name(state: Union[State, str, None]) -> Optional[str]:
    """Normalise a state specifier to its canonical string form."""
    if state is None:
        return None
    if isinstance(state, State):
        return state.full_name
    return str(state)


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------
class BaseStorage(ABC):
    """Interface every FSM backend implements. Keys are ``(user_id, chat_id)``."""

    @abstractmethod
    def get_state(self, user_id: int, chat_id: int = 0) -> Optional[str]:
        """Return the canonical state string, or None when no state is set."""

    @abstractmethod
    def set_state(self, user_id: int, chat_id: int, state: Optional[str]) -> None:
        """Persist ``state`` (None clears it)."""

    @abstractmethod
    def get_data(self, user_id: int, chat_id: int = 0) -> Dict[str, Any]:
        """Return a (copy of) the data dict stored for this key."""

    @abstractmethod
    def set_data(self, user_id: int, chat_id: int, data: Dict[str, Any]) -> None:
        """Replace the data dict for this key."""

    # ------------------------------------------------------------ conveniences
    def update_data(self, user_id: int, chat_id: int = 0, **kwargs: Any) -> Dict[str, Any]:
        """Merge ``kwargs`` into the stored data and return the full dict."""
        data = self.get_data(user_id, chat_id)
        data.update(kwargs)
        self.set_data(user_id, chat_id, data)
        return data

    def reset_state(self, user_id: int, chat_id: int = 0) -> None:
        self.set_state(user_id, chat_id, None)

    def clear(self, user_id: int, chat_id: int = 0) -> None:
        """Remove state *and* data for this key."""
        self.set_state(user_id, chat_id, None)
        self.set_data(user_id, chat_id, {})


class MemoryStorage(BaseStorage):
    """In-memory backend — the default. Not shared across processes; contents
    are lost when the process exits. Thread-safe via a lock."""

    def __init__(self) -> None:
        self._records: Dict[Tuple[int, int], Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _key(self, user_id: int, chat_id: int) -> Tuple[int, int]:
        return (int(chat_id or 0), int(user_id or 0))

    def get_state(self, user_id: int, chat_id: int = 0) -> Optional[str]:
        with self._lock:
            return self._records.get(self._key(user_id, chat_id), {}).get("state")

    def set_state(self, user_id: int, chat_id: int, state: Optional[str]) -> None:
        with self._lock:
            self._records.setdefault(self._key(user_id, chat_id), {})["state"] = state

    def get_data(self, user_id: int, chat_id: int = 0) -> Dict[str, Any]:
        with self._lock:
            return dict(self._records.get(self._key(user_id, chat_id), {}).get("data") or {})

    def set_data(self, user_id: int, chat_id: int, data: Dict[str, Any]) -> None:
        with self._lock:
            self._records.setdefault(self._key(user_id, chat_id), {})["data"] = dict(data)

    def clear(self, user_id: int, chat_id: int = 0) -> None:
        with self._lock:
            self._records.pop(self._key(user_id, chat_id), None)


class JSONFileStorage(BaseStorage):
    """A JSON-file backend: survives restarts, needs no infrastructure.

    Writes are atomic (``tmp file`` + ``os.replace``) so a crash mid-write can
    never corrupt the file. Intended for single-process bots with modest state
    volume.
    """

    def __init__(self, path: Union[str, os.PathLike[str]]) -> None:
        self._path = os.fspath(path)
        self._lock = threading.RLock()
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------ persistence
    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                self._records = json.load(fh)
        except (OSError, ValueError) as exc:
            logger.warning("Could not load FSM storage %s: %s — starting empty", self._path, exc)
            self._records = {}

    def _save(self) -> None:
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(self._records, fh, ensure_ascii=False)
        os.replace(tmp_path, self._path)

    @staticmethod
    def _key(user_id: int, chat_id: int) -> str:
        return f"{int(chat_id or 0)}:{int(user_id or 0)}"

    # -------------------------------------------------------------- interface
    def get_state(self, user_id: int, chat_id: int = 0) -> Optional[str]:
        with self._lock:
            return self._records.get(self._key(user_id, chat_id), {}).get("state")

    def set_state(self, user_id: int, chat_id: int, state: Optional[str]) -> None:
        with self._lock:
            self._records.setdefault(self._key(user_id, chat_id), {})["state"] = state
            self._save()

    def get_data(self, user_id: int, chat_id: int = 0) -> Dict[str, Any]:
        with self._lock:
            return dict(self._records.get(self._key(user_id, chat_id), {}).get("data") or {})

    def set_data(self, user_id: int, chat_id: int, data: Dict[str, Any]) -> None:
        with self._lock:
            self._records.setdefault(self._key(user_id, chat_id), {})["data"] = dict(data)
            self._save()

    def clear(self, user_id: int, chat_id: int = 0) -> None:
        with self._lock:
            self._records.pop(self._key(user_id, chat_id), None)
            self._save()


class RedisStorage(BaseStorage):
    """Redis backend for multi-process deployments.

    Requires the optional ``redis`` package: ``pip install gramlite[redis]``.
    One hash per ``(chat_id, user_id)`` keeps state and data together; keys are
    prefixed so a shared Redis instance can host several bots.
    """

    def __init__(self, redis_client: Any = None, *, url: Optional[str] = None,
                 prefix: str = "gramlite:fsm") -> None:
        if redis_client is None:
            try:
                import redis  # type: ignore[import-untyped]
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise ImportError(
                    "RedisStorage requires the 'redis' package. "
                    "Install it with:  pip install 'gramlite[redis]'"
                ) from exc
            redis_client = redis.Redis.from_url(url or "redis://localhost:6379/0")
        self._redis = redis_client
        self._prefix = prefix.rstrip(":")

    def _key(self, user_id: int, chat_id: int) -> str:
        return f"{self._prefix}:{int(chat_id or 0)}:{int(user_id or 0)}"

    def get_state(self, user_id: int, chat_id: int = 0) -> Optional[str]:
        value = self._redis.hget(self._key(user_id, chat_id), "state")
        return None if value in (None, b"", "") else value.decode() if isinstance(value, bytes) else str(value)

    def set_state(self, user_id: int, chat_id: int, state: Optional[str]) -> None:
        key = self._key(user_id, chat_id)
        if state is None:
            self._redis.hdel(key, "state")
        else:
            self._redis.hset(key, "state", state)

    def get_data(self, user_id: int, chat_id: int = 0) -> Dict[str, Any]:
        raw = self._redis.hget(self._key(user_id, chat_id), "data")
        if not raw:
            return {}
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            return dict(json.loads(raw))
        except ValueError:  # pragma: no cover - corrupted entry
            return {}

    def set_data(self, user_id: int, chat_id: int, data: Dict[str, Any]) -> None:
        self._redis.hset(self._key(user_id, chat_id), "data", json.dumps(data or {}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Filter glue
# ---------------------------------------------------------------------------
class StateFilter:
    """Matches messages while the sender sits in a given state.

    Created for you by ``@bot.message_handler(state=...)``; you rarely need to
    instantiate it directly.
    """

    name = "StateFilter"

    def __init__(self, bot: Any, state: Union[State, str]) -> None:
        self._bot = bot
        self._state = state

    def check(self, message: Any) -> bool:
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        if user is None:
            return False
        current = self._bot.get_state(user.id, getattr(chat, "id", 0) or 0)
        if self._state == "*":
            return True  # any state at all
        return current == state_full_name(self._state)
