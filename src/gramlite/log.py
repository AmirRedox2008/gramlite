"""Logging helpers.

The library logs to the ``gramlite`` logger namespace (``gramlite.client``,
``gramlite.handlers``, ``gramlite.polling``, ...) and stays silent unless the
host application configures logging::

    from gramlite import setup_logging
    setup_logging()                # INFO to stderr, pretty format
    setup_logging("DEBUG")         # verbose, to see every HTTP call
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

__all__ = ["setup_logging"]

DEFAULT_FORMAT = "%(asctime)s | %(name)s | %(levelname)-7s | %(message)s"
DEFAULT_DATEFMT = "%H:%M:%S"


def setup_logging(
    level: str = "INFO",
    fmt: str = DEFAULT_FORMAT,
    datefmt: str = DEFAULT_DATEFMT,
    stream: Optional[object] = None,
) -> logging.Logger:
    """Configure (once) and return the ``gramlite`` root logger.

    Safe to call multiple times — handlers are not duplicated.
    """
    logger = logging.getLogger("gramlite")
    logger.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
        handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        logger.addHandler(handler)
    return logger
