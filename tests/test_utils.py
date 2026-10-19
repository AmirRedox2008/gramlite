"""Tests for utility helpers: escaping, splitting, deep links."""

from __future__ import annotations

import pytest

from gramlite.utils import (
    MAX_MESSAGE_LENGTH,
    create_deep_link,
    escape_html,
    escape_markdown,
    split_text,
)


# ---------------------------------------------------------------------------
# Escaping
# ---------------------------------------------------------------------------
def test_escape_html_escapes_the_dangerous_three():
    assert escape_html("<b>tom & jerry</b>") == "&lt;b&gt;tom &amp; jerry&lt;/b&gt;"


def test_escape_markdown_v2_escapes_full_charset():
    raw = "a_b*c[d]e(f)g~h`i>j#k+l-m=n|o{p}q.r!s"
    escaped = escape_markdown(raw, version=2)
    for char in "_*[]()~`>#+-=|{}.!":
        assert f"\\{char}" in escaped
    assert escaped.count("\\") == len([c for c in raw if c in "_*[]()~`>#+-=|{}.!"])


def test_escape_markdown_v1_escapes_legacy_subset():
    assert escape_markdown("*bold* and _it_", version=1) == "\\*bold\\* and \\_it\\_"


# ---------------------------------------------------------------------------
# split_text
# ---------------------------------------------------------------------------
def test_split_text_short_text_is_single_chunk():
    assert split_text("hello") == ["hello"]


def test_split_text_empty_text_is_empty_list():
    assert split_text("") == []


def test_split_text_respects_limit():
    text = "word " * 2000  # 10 000 chars
    chunks = split_text(text)
    assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in chunks)
    # chunks are separate messages; the boundary space is the split point
    assert " ".join(chunks).split() == text.split()  # no words lost


def test_split_text_prefers_paragraph_boundaries():
    part1 = "para one\n\n"
    part2 = "para two\n\n"
    part3 = "para three"
    text = (part1 + part2 + part3) * 40
    chunks = split_text(text, limit=200)
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert any(chunk.startswith("para one") for chunk in chunks)


def test_split_text_hard_wraps_unbreakable_input():
    chunks = split_text("x" * 10_000, limit=1000)
    assert all(len(chunk) == 1000 for chunk in chunks[:-1])
    assert sum(len(chunk) for chunk in chunks) == 10_000


# ---------------------------------------------------------------------------
# Deep links
# ---------------------------------------------------------------------------
def test_create_deep_link_basic():
    assert (
        create_deep_link("mybot", "invite_42")
        == "https://t.me/mybot?start=invite_42"
    )


def test_create_deep_link_strips_at_and_supports_startgroup():
    link = create_deep_link("@mybot", "abc-123", start="startgroup")
    assert link == "https://t.me/mybot?startgroup=abc-123"


def test_create_deep_link_rejects_bad_start():
    with pytest.raises(ValueError):
        create_deep_link("bot", "x", start="join")


def test_create_deep_link_rejects_bad_payload():
    with pytest.raises(ValueError):
        create_deep_link("bot", "has space")
    with pytest.raises(ValueError):
        create_deep_link("bot", "x" * 65)
