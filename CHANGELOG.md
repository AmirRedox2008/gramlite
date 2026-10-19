# Changelog

## 2.0.0 — the "real framework" release

### Added
- **FSM module** (`gramlite.fsm`): `State` / `StateGroup`, `state=` handler filter,
  `bot.set_state / get_state / reset_state / get_state_data / update_state_data /
  clear_state_data`, and three storage backends: `MemoryStorage` (default),
  `JSONFileStorage` (atomic writes, survives restarts), `RedisStorage`
  (optional extra `gramlite[redis]`).
- **Middleware** (`gramlite.middleware`): `@bot.register_middleware(update_types=...)`
  chain-of-responsibility for sync and async bots, with short-circuit support.
- **Global exception handler**: `@bot.exception_handler` receives
  `(payload, exception)` for every unhandled handler/middleware crash.
- **Custom filters**: subclass `BaseFilter`, pass with `custom_filter=`.
- **`pass_args=True`**: command arguments forwarded to the handler
  (`/ban 42 spam` → `handler(message, "42", "spam")`).
- **New handler kinds**: `inline_query_handler`, `pre_checkout_query_handler`,
  `poll_handler`, `poll_answer_handler`, `my_chat_member_handler`,
  `chat_member_handler`, `chat_join_request_handler`.
- **New API methods** (sync + async parity): `send_poll`, `stop_poll`, `send_dice`,
  `send_venue`, `send_contact`, `send_animation`, `send_video_note`, `send_media_group`,
  `edit_message_caption`, `edit_message_reply_markup`, `pin/unpin_chat_message`,
  `get_chat_member_count`, `get_chat_member`, `get_chat_administrators`,
  `get_user_profile_photos`, `set_chat_title/description/permissions`,
  `restrict_chat_member`, `promote_chat_member`, `export/create/revoke_chat_invite_link`,
  `approve/decline_chat_join_request`, `leave_chat`, `log_out`, `close_api`,
  `set_my_commands`, `get_my_commands`, `delete_my_commands`, `set_my_name`,
  `set_my_description`, `set_my_short_description`, `answer_inline_query`,
  `answer_pre_checkout_query`, `download_file` (bytes).
- **New types**: `Poll`, `PollOption`, `PollAnswer`, `Dice`, `Venue`, `Invoice`,
  `SuccessfulPayment`, `PreCheckoutQuery`, `InlineQuery`, `ChatPermissions`, `ChatMember`,
  `ChatMemberUpdated`, `ChatJoinRequest`, `ChatInviteLink`, `BotCommand`,
  `UserProfilePhotos`, `InputMediaPhoto/Video`.
- **Typed error subclasses**: `BotBlockedError` (403), `InvalidTokenError` (401/404),
  `RateLimitError` (429, carries `retry_after`) — all still `ApiTelegramError` subclasses.
- **Threading**: `Bot(threaded=True, num_workers=8)` dispatches updates on a thread pool;
  `bot.stop_polling()`, `bot.close()`, sync context-manager support.
- **Helpers**: `bot.send_long_message` (auto 4096-split), `bot.parse_mode` default,
  cached `bot.user` / `bot.username`, `@botname` command-suffix verification,
  `utils.split_text / escape_html / escape_markdown / create_deep_link`, `setup_logging`.
- `prepare_params` now JSON-encodes lists/dicts (poll options, commands, media albums,
  entities) — previously only markup objects were encoded.
- `skip_pending` support in the async polling loop; `max_connections`/`secret_token`
  in `set_webhook`.

### Fixed
- **Async handlers were never awaited in v1** — the shared sync dispatcher called
  `async def` callbacks without awaiting. v2 introduces `AsyncHandlerRegistry`
  which awaits coroutine handlers and async middleware (regression test added).
- `process_update` now returns whether a matching handler actually ran.
- Wrong `sendVideoNote`/`sendAnimation` field names in the shared media uploader.
- Helpful error message typo in the `aiohttp` import hint.

### Tests
- Grew from 77 to 140+ offline tests: FSM, middleware, error taxonomy, new API
  surface, async awaiting regressions, threaded dispatch, utils.

## 0.1.0 — initial release

- Core: `Bot` (sync) + `AsyncBot` (aiohttp), ~30 API methods, media uploads,
  first-match-wins router with `commands / content_types / regexp / chat_types / func`
  filters, long-polling + infinity polling, webhook intake, 429/5xx retry policy,
  typed exception hierarchy, 40+ parsed types, keyboards, 77 offline tests, CI.
