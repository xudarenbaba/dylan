"""Text keys, term windows and secret masking. No tokenizer and no embeddings."""

from __future__ import annotations

import re

from dylan.memory.constants import (
    EVIDENCE_MIN_CHARS,
    MAX_TERM_CHARS,
    SECRET_MASK,
    SECRET_PATTERN,
    STOP_TERMS,
)

_TOKEN = re.compile(SECRET_PATTERN)
_PUNCT = r"\s，,。．.！!？?；;：:、“”\"'‘’（）()【】\[\]《》<>…~～—_/|·"
_SPLIT = re.compile(f"[{_PUNCT}]+")
_LOOSE = re.compile(f"[{_PUNCT}]+")


def key_of(text: str) -> str:
    """Drop whitespace and casefold Latin letters. Chinese stays as written."""
    joined = "".join(str(text).split())
    return "".join(char.casefold() if char.isascii() else char for char in joined)


def loose(text: str) -> str:
    return key_of(_LOOSE.sub("", str(text)))


def contains_quote(source: str, quote: str) -> bool:
    needle = loose(quote)
    if len(needle) < EVIDENCE_MIN_CHARS:
        return False
    return needle in loose(source)


def windows(text: str, longest: int = MAX_TERM_CHARS) -> set[str]:
    """Every short run of characters inside one clause. Lookups use exact keys."""
    found: set[str] = set()
    for segment in _SPLIT.split(str(text)):
        seg = key_of(segment)
        size = len(seg)
        for start in range(size):
            for end in range(start + 1, min(size, start + longest) + 1):
                piece = seg[start:end]
                if len(piece) == 1 and piece.isascii():
                    continue
                found.add(piece)
    return found - STOP_TERMS


def clip(value: object, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit]


def has_secret(text: str, api_key: str) -> bool:
    if api_key and api_key in text:
        return True
    return _TOKEN.search(text) is not None


def mask_secrets(text: str, api_key: str) -> tuple[str, bool]:
    masked = text
    if api_key and api_key in masked:
        masked = masked.replace(api_key, SECRET_MASK)
    masked = _TOKEN.sub(SECRET_MASK, masked)
    return masked, masked != text
