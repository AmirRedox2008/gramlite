# GramLite — Architecture

This document explains how GramLite is built and **why** each decision was
made. It doubles as an interview preparation sheet: every section answers a
question a senior engineer would realistically ask.

## 1. Layered design

```
┌────────────────────────────────────────────────────────────┐
│  your code                                                 │
│  @bot.message_handler(...)  /  await bot.send_message(...) │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│  bot.py (Bot) / async_bot.py (AsyncBot)                    │
│  · 55+ Bot API methods, snake_case                         │
│  · media helpers (file_id | URL | file-like | path)        │
│  · FSM API · threaded dispatch · polling / webhooks        │
└───────────────┬───────────────────────┬────────────────────┘
                │                       │
┌───────────────▼──────────┐  ┌─────────▼──────────────────┐
│  handlers.py             │  │  api_client.py             │
│  Handler · filters       │  │  APIClient (requests)      │
│  HandlerRegistry         │  │  AsyncAPIClient (aiohttp)  │
│  AsyncHandlerRegistry    │  │  retry · 429 · backoff     │
│  first-match-wins router │  │  typed 401/403/429 errors  │
├──────────────────────────┤  └─────────┬──────────────────┘
│  middleware.py           │            │
│  chain-of-responsibility │            │
├──────────────────────────┤            │
│  fsm.py                  │            │
│  State · StateGroup      │            │
│  Memory/JSONFile/Redis   │            │
└───────────────┬──────────┘            │
┌───────────────▼───────────────────────▼──────────────────┐
│  types.py — TelegramObject base                          │
│  User · Chat · Message · Update · Poll · ChatMember · ... │
│  keyboards + input media (request-side, JSON)            │
├──────────────────────────────────────────────────────────┤
│  exceptions.py — TelegramError hierarchy                 │
└──────────────────────────────────────────────────────────┘
```

Key property: **types and routing are shared** between the sync and async
stacks. There is exactly one parser for every Telegram object; the async twin
replaces the transport *and* the dispatcher (to await coroutines), nothing else.

## 2. Life of an update (polling)

1. `run_polling()` calls `bot.get_updates(offset=...)` with long-polling
   (`timeout` — the HTTP request is held open by Telegram for up to N seconds).
2. The raw JSON list is parsed into `Update` objects.
3. `HandlerRegistry.process_update()` finds which payload the update carries
   (`message`, `edited_message`, `channel_post`, `callback_query`, ...).
4. Handlers for that payload type are checked **in registration order**; the
   first one whose filters all pass is executed.
5. `offset = update_id + 1` — Telegram's contract for acknowledging updates.
   A `skip_pending` option probes with `offset=-1` (only the last update) to
   drop the backlog after a restart.

For webhooks there is no step 1–2: the web framework hands the JSON body to
`process_new_updates()`, and steps 3–5 (minus offset bookkeeping, which the
webhook contract makes unnecessary) are identical.

## 3. Design decisions

| Decision | Why |
|---|---|
| **Session/client injection** (`Bot(client=...)`, `APIClient(session=...)`) | Connection pooling in production; zero-network unit tests in CI. Every test in this repo runs offline because the transport is a seam. |
| **First-match-wins routing** | Predictable priority (specific handlers registered first), low magic, matches the mental model of pyTelegramBotAPI. Alternative (aiogram-style routers) adds indirection a small framework does not need. |
| **Handler exceptions are logged, not raised** | One broken handler can never kill the polling loop — the polling process is the availability domain of the bot. Trade-off: bugs surface in logs, not stack traces in your face; mitigated by `logger.exception` with full traceback. |
| **Missing fields return `None`** (`__getattr__` fallback) | Telegram adds fields constantly; strict models would break on every Bot API release. Unknown fields are preserved as attributes too. Trade-off: typos resolve to `None` silently. |
| **`Message.from` → `from_user`** | `from` is a Python keyword. Same rename the whole ecosystem uses. |
| **Retry only `429` and `5xx`** | `4xx` are caller bugs (bad chat_id, wrong markdown) — retrying would hide them. `retry_after` from Telegram is honoured exactly; other failures use exponential back-off. |
| **Network errors raise immediately** (`NetworkError`) | The polling loop already retries at a higher level; double-retrying inside the client would multiply latency during outages. |
| **`AsyncBot` imports lazily** (PEP 562 `__getattr__`) | `aiohttp` is optional; sync users pay nothing. `pip install "gramlite[async]"` unlocks it. |
| **Booleans are sent as `True`/`False` form values** | Matches what `requests` does with `data=` dicts and what Telegram's parser accepts in production (verified against pyTelegramBotAPI's behaviour). |
| **`py.typed` marker** | Downstream projects get accurate type hints; forces the codebase to stay honest about annotations. |

## 3b. v2 decisions (FSM, middleware, async dispatcher)

| Decision | Why |
|---|---|
| **Two registries, one `Handler`** | v1 called callbacks synchronously — `async def` handlers silently never ran. v2 splits dispatch: `HandlerRegistry` (sync) and `AsyncHandlerRegistry` (awaits coroutine callbacks *and* async middleware). Registration, filters and types stay shared: one source of truth, two execution models. A regression test pins this. |
| **FSM state is a string, not an enum** | Telegram itself is schema-less; states must survive process restarts and cross languages. `StateGroup` only exists to auto-name states (`Form:name`) and give nice `state=Form.name` ergonomics. |
| **FSM keys are `(chat_id, user_id)`** | The same user has independent conversations per chat — matching aiogram's semantics while keeping the storage API 2-argument simple. |
| **`JSONFileStorage` writes are atomic** (tmp + `os.replace`) | A crash mid-write can never corrupt the state file; `os.replace` is atomic on POSIX and Windows. |
| **State filter is a normal `BaseFilter`** | No special-case code in the router: `state=` is merged into the handler's custom-filter chain at registration time. The dispatcher stays filter-agnostic. |
| **Middleware wraps dispatch, not individual handlers** | One middleware call per update payload (not per attempted handler) — cheap, predictable order, and short-circuiting (not calling `next_()`) reliably mutes the update. |
| **Middleware/handler exceptions funnel into one hook** | `@bot.exception_handler(payload, exception)` replaces `try/except` boilerplate in every handler; falls back to `logger.exception` so nothing is ever swallowed silently. |
| **`process_update` returns whether a handler ran** | Lets polling/webhook layers (and tests) observe delivery; middleware authors should `return next_()` to propagate the boolean. |
| **Threading is opt-in** (`threaded=True`) | Predictable ordering by default; a `ThreadPoolExecutor` when you want concurrency. Opt-in keeps tests deterministic and makes the concurrency model explicit rather than accidental. |
| **`@botname` suffix is verified against `getMe`** | `/start@otherbot` in a group must not trigger this bot. The username is fetched lazily once — and only when command handlers exist — to avoid a startup API call for bots that don't need it. |
| **`prepare_params` JSON-encodes any list/dict** | Telegram's multipart/form endpoints require JSON *strings* for `options`, `commands`, `media`, `entities`; encoding centrally prevents each wrapper from hand-rolling `json.dumps`. |

## 4. Concurrency model

- **Sync `Bot`**: `run_polling()` is a single-threaded loop; handlers execute
  sequentially by default. `Bot(threaded=True, num_workers=N)` dispatches each
  update on a `ThreadPoolExecutor` — handlers may interleave, so only enable it
  for stateless handlers or guard shared data. `bot.stop_polling()` signals the
  loop through a `threading.Event` (takes effect within one long-poll cycle).
- **`infinity_polling()`**: wraps `run_polling()`; any crash is logged and the
  loop restarts with exponential back-off (capped at `max_backoff=60s`).
  `KeyboardInterrupt` exits cleanly.
- **Async `AsyncBot`**: one `aiohttp.ClientSession` per bot, created lazily
  and closed by `close()` / `async with`. Polling uses `asyncio.Event` for
  cancellation; `infinity_polling()` re-raises `CancelledError` so task
  cancellation is never swallowed. Updates are processed sequentially per
  loop iteration — `async def` handlers are awaited in order.

## 5. Testing strategy

| Layer | Fake | What is asserted |
|---|---|---|
| Transport (`APIClient`) | `FakeSession` (replaces `requests.Session`) | URL shape, param serialisation, retry counts & delays, typed exceptions |
| Facade (`Bot`) | `RecordingClient` (replaces `APIClient`) | method→params mapping, response parsing, media upload tuples |
| Routing (`HandlerRegistry`) | none needed (pure logic) | every filter, ordering, exception containment |
| Polling | duck-typed bot stub + `FakeStop` event | offset bookkeeping, `skip_pending`, crash restart, back-off |
| Async | `FakeAsyncClient` + `asyncio.run` | same as sync, plus session lifecycle |

No test touches the network; the whole suite runs in ~0.5 s, which keeps the
feedback loop compatible with CI on every push (GitHub Actions, Python
3.10–3.13).

## 6. How to extend — adding a new API method

1. Find the method in the [Bot API reference](https://core.telegram.org/bots/api)
   (e.g. `sendPoll`).
2. Add a thin wrapper to `bot.py` (and `async_bot.py` if useful) — the
   parameter dict is passed through `prepare_params`, which drops `None`s and
   serialises keyboards:

```python
def send_poll(self, chat_id, question, options, **kwargs):
    return Message.de_json(self.client.request("sendPoll", {
        "chat_id": chat_id, "question": question,
        "options": json.dumps(options), **kwargs,
    }))
```

3. Add a test that pins the method name and params mapping.

That is the whole protocol layer: **one wrapper method per endpoint**, everything
else (serialisation, retries, errors, typing) is already handled below it.
