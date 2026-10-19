"""Long-polling loops for the synchronous bot.

Two layers of resilience:

* :func:`run_polling` survives API-level hiccups (``429``, ``5xx``, network
  errors) and keeps the ``offset`` bookkeeping correct;
* :func:`run_infinity_polling` wraps it and restarts the whole loop when
  anything unexpected happens, with exponential back-off.

Both accept a ``dispatch`` callable (the Bot's ``_dispatch_update``) so
handler execution can be threaded without the loop knowing about it.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Iterable, Optional

from .exceptions import ApiTelegramError, NetworkError

logger = logging.getLogger("gramlite.polling")

__all__ = ["run_infinity_polling", "run_polling"]


def run_polling(
    bot: Any,
    router: Any,
    *,
    interval: float = 0,
    long_polling_timeout: int = 10,
    allowed_updates: Optional[Iterable[str]] = None,
    stop_event: Optional[threading.Event] = None,
    skip_pending: bool = False,
    retry_wait: float = 1.0,
    dispatch: Optional[Callable[[Any], Any]] = None,
) -> int:
    """Run the ``getUpdates`` loop until ``stop_event`` is set.

    ``dispatch(update)`` defaults to ``router.process_update``. Returns the
    final offset so callers can resume exactly where they left.
    """
    stop = stop_event or threading.Event()
    offset = 0
    deliver = dispatch or router.process_update

    if skip_pending:
        # ``offset=-1`` returns only the very last update: everything older
        # is dropped, which is what users expect after a restart.
        try:
            updates = bot.get_updates(offset=-1, timeout=0)
            if updates:
                offset = updates[-1].update_id + 1
                logger.info("Skipping pending updates — resuming at offset %d", offset)
        except (ApiTelegramError, NetworkError) as exc:
            logger.warning("skip_pending probe failed: %s", exc)

    while not stop.is_set():
        try:
            updates = bot.get_updates(
                offset=offset or None,
                timeout=long_polling_timeout,
                allowed_updates=allowed_updates,
            )
        except (ApiTelegramError, NetworkError) as exc:
            logger.error("getUpdates failed: %s — retrying in %.1fs", exc, retry_wait)
            if stop.wait(retry_wait):
                break
            continue

        for update in updates:
            deliver(update)
            offset = update.update_id + 1

        if interval and not stop.is_set():
            stop.wait(interval)

    logger.info("Polling stopped at offset %d", offset)
    return offset


def run_infinity_polling(
    bot: Any,
    router: Any,
    *,
    interval: float = 0,
    long_polling_timeout: int = 10,
    allowed_updates: Optional[Iterable[str]] = None,
    stop_event: Optional[threading.Event] = None,
    skip_pending: bool = False,
    max_backoff: float = 60.0,
    dispatch: Optional[Callable[[Any], Any]] = None,
) -> None:
    """Like :func:`run_polling`, but restarts on any unexpected crash."""
    stop = stop_event or threading.Event()
    backoff = 1.0

    while not stop.is_set():
        try:
            run_polling(
                bot, router,
                interval=interval,
                long_polling_timeout=long_polling_timeout,
                allowed_updates=allowed_updates,
                stop_event=stop,
                skip_pending=skip_pending,
                dispatch=dispatch,
            )
            break  # clean shutdown
        except KeyboardInterrupt:
            logger.info("Interrupted by user — shutting down.")
            break
        except Exception as exc:  # noqa: BLE001 - that is the whole point
            logger.error("Polling crashed: %s — restarting in %.0fs", exc, backoff)
            stop.wait(min(backoff, max_backoff))
            backoff = min(backoff * 2, max_backoff)
