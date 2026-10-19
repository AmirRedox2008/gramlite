"""Utility helpers: escaping, text splitting and deep links."""

from __future__ import annotations

from typing import List

__all__ = [
    "create_deep_link",
    "escape_html",
    "escape_markdown",
    "split_text",
]

#: Telegram's hard limit for a single message's text/caption length.
MAX_MESSAGE_LENGTH = 4096


def escape_html(text: str) -> str:
    """Escape a string for safe use inside HTML parse-mode messages."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def escape_markdown(text: str, version: int = 2) -> str:
    """Escape a string for safe use inside Markdown / MarkdownV2 messages.

    ``version=2`` escapes the full MarkdownV2 character set; ``version=1``
    escapes the legacy subset (``* _ ` [``).
    """
    text = str(text)
    if version == 2:
        for char in (
            "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!",
        ):
            text = text.replace(char, f"\\{char}")
        return text
    for char in ("*", "_", "`", "["):
        text = text.replace(char, f"\\{char}")
    return text


def split_text(text: str, limit: int = MAX_MESSAGE_LENGTH) -> List[str]:
    """Split a long text into Telegram-sized chunks (≤ ``limit`` chars).

    Splits at paragraph boundaries first (blank lines), then newlines, then
    hard-wraps at ``limit`` — so chunks stay as readable as possible. Empty
    input returns ``[]``; short input returns a single chunk.
    """
    text = str(text or "")
    if len(text) <= limit:
        return [text] if text else []

    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        window = remaining[:limit + 1]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n").lstrip()
    return [chunk for chunk in chunks if chunk]


def create_deep_link(username: str, payload: str, start: str = "start") -> str:
    """Build a ``t.me`` deep link: ``https://t.me/<bot>?start=<payload>``.

    ``start`` may be ``"start"``, ``"startgroup"`` or ``"startattach"``;
    ``payload`` may contain ``A-Z a-z 0-9 _ -`` (max 64 chars, per Bot API).
    """
    if start not in ("start", "startgroup", "startattach"):
        raise ValueError("start must be one of: start, startgroup, startattach")
    payload = str(payload)
    if not payload or len(payload) > 64 or not all(
        ch.isalnum() or ch in "_-" for ch in payload
    ):
        raise ValueError("payload must be 1-64 chars of [A-Za-z0-9_-]")
    return f"https://t.me/{str(username).lstrip('@')}?{start}={payload}"
