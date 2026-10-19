# 🦅 GramLite

**A lightweight Telegram Bot API framework written completely from scratch — sync + async, FSM, middleware, inline mode.**

> GramLite is not a wrapper around pyTelegramBotAPI or aiogram. Every layer — HTTP transport,
> retry policy, type parsing, router, filters, FSM, middleware — is implemented in ~2,700 lines
> of typed, tested Python with only `requests` as the runtime dependency.

![CI](https://github.com/AmirRedox2008/gramlite/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-140%2B%20offline-brightgreen)

---

## Why GramLite

| | GramLite | pyTelegramBotAPI | aiogram |
|---|---|---|---|
| Core dependency | `requests` only | `requests` only | `aiohttp` + `pydantic` + ... |
| Sync **and** async APIs | ✅ shared types/filters | ✅ | ❌ async only |
| FSM (states) | ✅ 3 storages built-in | ➕ addon, separate package | ✅ |
| Middleware | ✅ sync + async | ❌ | ✅ |
| Learning curve | tiny (one file per concept) | medium | steep |
| Code size to read end-to-end | ~2.7k lines | ~20k lines | ~15k lines |

The point of this project is **demonstrating how a framework works**, not replacing the mature
libraries: clean layering, honest trade-offs, and a test suite that runs fully offline.

## Features

- **Full sync (`Bot`) and async (`AsyncBot`) APIs** sharing one router, one filter model and one
  type system — write a handler once, port it by changing one keyword.
- **50+ Bot API methods**: messages, media uploads (path / bytes / file-like / file_id / URL),
  albums, polls, dice, venues, contacts, chat administration, invite links, join requests,
  commands & profile management, inline mode, payments pre-checkout.
- **Handler system** with first-match-wins routing and AND-combined filters:
  `commands`, `content_types`, `regexp`, `chat_types`, `state`, `func`, `custom_filter`, `pass_args`.
- **12 update kinds** routed: messages, edits, channel posts, callbacks, inline queries,
  pre-checkout, polls, poll answers, join requests, member updates.
- **FSM** for multi-step conversations with pluggable storage:
  `MemoryStorage` (default), `JSONFileStorage` (atomic writes, survives restarts),
  `RedisStorage` (multi-process).
- **Middleware** chain-of-responsibility (sync + async) with short-circuit support.
- **Typed exceptions**: `BotBlockedError`, `InvalidTokenError`, `RateLimitError` (carries
  `retry_after`), `ApiHTTPError`, `NetworkError`.
- **Resilient transport**: automatic retries on `429`/`5xx` honouring Telegram's `retry_after`,
  exponential back-off, connection pooling via injected sessions.
- **Utilities**: Markdown/HTML escaping, smart 4096-char message splitting
  (`send_long_message`), deep links, `download_file` → bytes, one-line `setup_logging`.
- **Threaded dispatch** (opt-in), `stop_polling()`, graceful `infinity_polling` restarts.

## Installation

```bash
pip install gramlite           # sync only (requests)
pip install "gramlite[async]"  # + async support (aiohttp)
pip install "gramlite[redis]"  # + Redis FSM storage
```

Or from source: `pip install -e .`

## Quick start

```python
from gramlite import Bot

bot = Bot("TOKEN", parse_mode="HTML")

@bot.message_handler(commands=["start"])
def welcome(message):
    bot.reply_to(message, f"Hi, <b>{message.from_user.full_name}</b>!")

@bot.message_handler(commands=["ban"], pass_args=True)
def ban(message, *args):
    user_id = int(args[0])
    bot.ban_chat_member(message.chat.id, user_id)
    bot.reply_to(message, "Done.")

@bot.message_handler(content_types=["photo"])
def photos(message):
    file_id = message.photo[-1].file_id
    bot.reply_to(message, "Nice shot!", reply_to_message_id=message.message_id)
    bot.send_photo(message.chat.id, file_id)

bot.infinity_polling()
```

### Async twin

```python
import asyncio
from gramlite import AsyncBot

bot = AsyncBot("TOKEN")

@bot.message_handler(commands=["start"])
async def welcome(message):
    await bot.reply_to(message, "Hello async world!")

asyncio.run(bot.infinity_polling())
```

### FSM — multi-step conversations

```python
from gramlite import Bot
from gramlite.fsm import State, StateGroup, JSONFileStorage

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
    bot.reply_to(message, f"Registered: {data.get('name')}, {message.text}")

bot.infinity_polling()
```

### Middleware & error handling

```python
import logging

@bot.register_middleware(update_types=["message"])
def log_messages(message, next_):
    logging.info("msg from %s", message.from_user.id)
    next_()               # omit to short-circuit (handler never runs)

@bot.exception_handler
def on_error(payload, exception):
    logging.exception("Unhandled error in %s", payload)

try:
    bot.send_message(chat_id, "Hi")
except BotBlockedError:
    ...                   # user blocked the bot
except RateLimitError as e:
    time.sleep(e.retry_after)
```

### Inline mode & polls

```python
@bot.inline_query_handler()
def inline(query):
    bot.answer_inline_query(query.id, [{
        "type": "article", "id": "1", "title": f"Echo: {query.query}",
        "input_message_content": {"message_text": query.query},
    }], cache_time=1)

@bot.poll_answer_handler()
def vote(answer):
    ...
```

### Webhook (Flask)

```python
@app.route("/webhook", methods=["POST"])
def webhook():
    bot.process_webhook_update(request.get_json(force=True))
    return "ok"
```

## Filters reference (message handlers)

| filter | example | meaning |
|---|---|---|
| `commands` | `commands=["start", "help"]` | `/start` or `/start@yourbot` |
| `content_types` | `content_types=["photo", "video"]` (or `["all"]`) | payload type |
| `regexp` | `regexp=r"\d+"` | `re.search` on the text |
| `chat_types` | `chat_types=["private"]` | chat type |
| `state` | `state=Form.name`, `state="*"` | FSM state |
| `func` | `func=lambda m: "hi" in m.text` | any predicate |
| `custom_filter` | `custom_filter=AdminFilter()` | reusable `BaseFilter` subclass |
| `pass_args` | `pass_args=True` | `/ban 42 spam` → `handler(m, "42", "spam")` |

Callback handlers additionally support `regexp` against `callback_query.data`.

## Project layout

```
src/gramlite/
├── bot.py          # sync facade: 50+ methods, FSM, threading, polling
├── async_bot.py    # async twin: same surface, awaited handlers/middleware
├── api_client.py   # HTTP transport: retries, back-off, typed errors
├── handlers.py     # router, filters, dispatch (sync + async registries)
├── middleware.py   # chain-of-responsibility (sync + async)
├── fsm.py          # states + Memory/JSONFile/Redis storages
├── polling.py      # long-polling loops with crash recovery
├── types.py        # 40+ parsed Telegram types + keyboards
├── exceptions.py   # typed error hierarchy
├── utils.py        # escaping, splitting, deep links
└── log.py          # setup_logging
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the layer diagram, design decisions and the
testing strategy — it doubles as interview material.

## Tests

The whole suite (140+ tests) runs **fully offline** against fake transports:

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

- [x] v1: core, sync+async, 30 methods, CI
- [x] v2: FSM, middleware, inline mode, payments, admin surface, error taxonomy
- [ ] Conversation shortcuts (`bot.register_next_step_handler`)
- [ ] Local Bot API server file helpers (large uploads)
- [ ] `LinkPreviewOptions` / Bot API 7.x+ fields
- [ ] Publish to PyPI

## Acknowledgements

Design inspiration: **pyTelegramBotAPI** (handler ergonomics) and **aiogram** (FSM & middleware
concepts). Implemented from scratch, no source copied.

## License

MIT — see [LICENSE](LICENSE).
