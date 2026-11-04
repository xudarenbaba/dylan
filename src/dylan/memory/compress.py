"""Extractive summaries and visible-text selection. Storage changes only on demotion."""

from __future__ import annotations

from datetime import datetime

from dylan.clock import days_between, load_time
from dylan.memory.constants import (
    COMPRESS_MAX_CONDUCTIVITY,
    COMPRESS_MIN_AGE_DAYS,
    ESSENCE_CHARS,
    GHOST_CHARS,
    SUMMARY_CHARS,
)
from dylan.memory.model import Fiber


def _sentences(text: str) -> list[str]:
    if not text:
        return []
    pieces: list[str] = []
    buf: list[str] = []
    for char in text:
        buf.append(char)
        if char in "。！？!?":
            pieces.append("".join(buf).strip())
            buf = []
    tail = "".join(buf).strip()
    if tail:
        pieces.append(tail)
    return [piece for piece in pieces if piece]


def summarize(text: str) -> tuple[str, str, str]:
    sentences = _sentences(text)
    summary = "".join(sentences[:2]) if sentences else text
    summary = summary[:SUMMARY_CHARS]
    essence_source = sentences[0] if sentences else summary
    essence = essence_source[:ESSENCE_CHARS]
    ghost = essence[:GHOST_CHARS]
    return summary, essence, ghost


def age_form(days: float) -> int:
    if days < 7:
        return 0
    if days < 30:
        return 1
    if days < 180:
        return 2
    return 3


def visible_text(fiber: Fiber, now: datetime) -> str:
    if fiber.compression_tier >= 4:
        return _metadata(fiber)
    days = max(0.0, days_between(load_time(fiber.created_at), now))
    index = max(age_form(days), min(fiber.compression_tier, 3))
    fields = [fiber.body or "", fiber.summary, fiber.essence, fiber.ghost]
    while index >= 0:
        if fields[index]:
            return fields[index]
        index -= 1
    return _metadata(fiber)


def _metadata(fiber: Fiber) -> str:
    tags = ",".join(fiber.tags)
    return f"{fiber.memory_type} {fiber.created_at} {tags}".strip()


def demote(fiber: Fiber, now: datetime, *, explicit: bool) -> Fiber:
    if fiber.conductivity >= COMPRESS_MAX_CONDUCTIVITY:
        return fiber
    conducted = fiber.last_conducted_at or fiber.created_at
    age = days_between(load_time(conducted), now)
    if age < COMPRESS_MIN_AGE_DAYS:
        return fiber
    if fiber.compression_tier >= 4:
        return fiber
    if fiber.compression_tier == 3:
        if not explicit:
            return fiber
        return fiber.model_copy(
            update={
                "compression_tier": 4,
                "body": None,
                "summary": "",
                "essence": "",
                "ghost": "",
            }
        )
    summary, essence, ghost = summarize(fiber.body or fiber.summary)
    return fiber.model_copy(
        update={
            "compression_tier": fiber.compression_tier + 1,
            "summary": summary or fiber.summary,
            "essence": essence or fiber.essence,
            "ghost": ghost or fiber.ghost,
        }
    )


def promote_tier(fiber: Fiber) -> Fiber:
    if fiber.compression_tier <= 0 or fiber.compression_tier >= 4:
        return fiber
    if fiber.compression_tier == 4 or not (fiber.body or fiber.summary or fiber.essence):
        return fiber
    return fiber.model_copy(update={"compression_tier": fiber.compression_tier - 1})
