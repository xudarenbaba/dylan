"""How a memory looks when it comes to mind: clarity first, then what is left of it."""

from __future__ import annotations

from datetime import datetime, tzinfo

from dylan.clock import load_time, short_day, short_minute
from dylan.memory.constants import CLARITY, MEMORY_TYPES, SOURCES
from dylan.memory.model import Fiber

_DETAIL_SHOWN = 120


def content(fiber: Fiber) -> str:
    kind = MEMORY_TYPES.get(fiber.memory_type, "事")
    if fiber.detail_level >= 3:
        return f"只记得有过这么一回事（{kind}），内容想不起来了"
    if fiber.detail_level == 2:
        return fiber.gist or fiber.statement[:20]
    text = fiber.statement or fiber.gist
    if fiber.detail_level == 0 and fiber.detail and fiber.detail not in text:
        text = f"{text}；原话「{fiber.detail[:_DETAIL_SHOWN]}」"
    return text


def when(fiber: Fiber, tz: tzinfo) -> str:
    if fiber.occurred_start:
        start = load_time(fiber.occurred_start)
        end = load_time(fiber.occurred_end) if fiber.occurred_end else start
        if (end - start).total_seconds() > 86400:
            return f"{short_day(start, tz)}到{short_day(end, tz)}"
        return short_day(start, tz)
    return f"{short_day(load_time(fiber.created_at), tz)}记下"


def describe(fiber: Fiber, clarity_key: str, tz: tzinfo, now: datetime) -> str:
    notes = [SOURCES.get(fiber.source, fiber.source), when(fiber, tz)]
    if fiber.emotion is not None:
        notes.append(f"{fiber.emotion.who}感到{fiber.emotion.label}")
    if fiber.memory_type == "plan":
        if fiber.due_at:
            due = load_time(fiber.due_at)
            notes.append(f"{'原定' if due < now else '定在'}{short_minute(due, tz)}")
        if fiber.trigger:
            notes.append(f"等到{fiber.trigger}")
    if fiber.state == "done":
        notes.append("已经完成")
    if fiber.state == "superseded" and fiber.valid_until:
        notes.append(f"到{short_day(load_time(fiber.valid_until), tz)}为止")
    kind = MEMORY_TYPES.get(fiber.memory_type, fiber.memory_type)
    label = CLARITY.get(clarity_key, clarity_key)
    return f"{label}｜{kind}｜{content(fiber)}（{'，'.join(notes)}）"


def fit(lines: list[str], budget: int) -> list[str]:
    """Whole lines in order until the budget runs out. Nothing is cut in the middle."""
    kept: list[str] = []
    used = 0
    for line in lines:
        cost = len(line) + (1 if kept else 0)
        if used + cost > budget:
            continue
        kept.append(line)
        used += cost
    return kept
