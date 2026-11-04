"""What is always on her mind: time, mood, last time, him, what she is waiting for, herself."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from dylan.clock import days_between, load_time, local_stamp
from dylan.memory.constants import (
    AWARENESS_CHARS,
    PLAN_AWARE_AHEAD_DAYS,
    PLAN_AWARE_OVERDUE_DAYS,
    SELF_AWARE_LIMIT,
    STATUS_AWARE_DAYS,
)
from dylan.memory.model import Fiber
from dylan.memory.physiology import clarity, current_mood
from dylan.memory.render import describe, fit
from dylan.memory.store import MemoryStore

_ABOUT_HIM = ("agreement", "fact", "preference", "habit")
_PER_SECTION = 8


@dataclass
class Awareness:
    text: str
    fiber_ids: list[str] = field(default_factory=list)


def gap_text(hours: float) -> str:
    if hours < 1:
        return "不到一小时"
    if hours < 23.5:
        return f"大约 {max(1, round(hours))} 小时"
    return f"大约 {max(1, round(hours / 24))} 天"


def build_awareness(
    store: MemoryStore,
    tz: tzinfo,
    *,
    current_session: str | None = None,
    budget: int = AWARENESS_CHARS,
) -> Awareness:
    now = store.clock.now()
    meta = store.meta()
    user = store.neuron(meta["user_id"])
    his = user.name if user else "他"
    head = [f"现在是 {local_stamp(now, tz)}（本地时间）。"]
    born = days_between(load_time(meta["created_at"]), now)
    head.append(f"今天是你被创造出来的第 {int(born) + 1} 天。")
    if meta["last_session_end"]:
        hours = days_between(load_time(meta["last_session_end"]), now) * 24
        head.append(f"距离上次和{his}聊天过去了{gap_text(hours)}。")
    else:
        head.append(f"这是你第一次和{his}聊天。")
    mood = current_mood(store.mood(), now)
    if mood is not None:
        cause = f"，因为{mood.cause}" if mood.cause else ""
        head.append(f"你现在的心情：{mood.label}{cause}。")
    else:
        head.append(f"你现在的心情平稳，底色是{meta['baseline_mood']}。")
    aliases = store.aliases().get(meta["user_id"], [])
    if aliases:
        head.append(f"{his}也被叫作：{'、'.join(aliases[:4])}。")

    fibers = store.fibers({"active"})
    conflicted = _conflicted(store, fibers)
    sections: list[tuple[str, list[Fiber]]] = [
        ("心里惦记的事", _waiting(fibers, conflicted, now)),
        (f"关于{his}", _about_him(fibers, meta["user_id"], now)),
        ("关于你自己", _about_self(fibers, meta["self_id"])),
    ]
    lines = list(head)
    last = _last_time(store, current_session)
    if last:
        lines.append(f"上次聊天：{last}")
    chosen: list[str] = []
    remaining = budget - sum(len(line) + 1 for line in lines)
    for title, items in sections:
        rendered: list[str] = []
        picked: list[str] = []
        for fiber in items[:_PER_SECTION]:
            if fiber.id in chosen:
                continue
            seen = clarity(fiber, conflicted=fiber.id in conflicted)
            rendered.append("- " + describe(fiber, seen, tz, now))
            picked.append(fiber.id)
        kept = fit(rendered, max(0, remaining - len(title) - 2))
        if not kept:
            continue
        lines.append(f"{title}：")
        lines.extend(kept)
        remaining -= len(title) + 2 + sum(len(line) + 1 for line in kept)
        chosen.extend(fiber_id for fiber_id, line in zip(picked, rendered) if line in kept)
    return Awareness(text="\n".join(lines), fiber_ids=chosen)


def _rank(fiber: Fiber) -> float:
    return fiber.importance * fiber.strength


def _about_him(fibers: list[Fiber], user_id: str, now: datetime) -> list[Fiber]:
    lasting = [
        fiber
        for fiber in fibers
        if fiber.memory_type in _ABOUT_HIM and fiber.about in {user_id, "both"}
    ]
    recent = [
        fiber
        for fiber in fibers
        if fiber.memory_type == "status"
        and fiber.about in {user_id, "both"}
        and now - load_time(fiber.updated_at) <= timedelta(days=STATUS_AWARE_DAYS)
    ]
    ordered = sorted(lasting, key=_rank, reverse=True)
    return sorted(recent, key=_rank, reverse=True)[:3] + ordered


def _about_self(fibers: list[Fiber], self_id: str) -> list[Fiber]:
    mine = [fiber for fiber in fibers if fiber.memory_type == "self" or (
        fiber.about == self_id and fiber.memory_type in {"preference", "habit"}
    )]
    return sorted(mine, key=_rank, reverse=True)[:SELF_AWARE_LIMIT]


def _waiting(fibers: list[Fiber], conflicted: set[str], now: datetime) -> list[Fiber]:
    plans: list[Fiber] = []
    for fiber in fibers:
        if fiber.memory_type != "plan":
            continue
        if fiber.due_at:
            due = load_time(fiber.due_at)
            if now - timedelta(days=PLAN_AWARE_OVERDUE_DAYS) <= due <= now + timedelta(
                days=PLAN_AWARE_AHEAD_DAYS
            ):
                plans.append(fiber)
        elif fiber.trigger:
            plans.append(fiber)
    plans.sort(key=lambda fiber: fiber.due_at or "9999")
    disputes = sorted(
        (fiber for fiber in fibers if fiber.id in conflicted), key=_rank, reverse=True
    )
    return plans[:4] + disputes[:4]


def _conflicted(store: MemoryStore, fibers: list[Fiber]) -> set[str]:
    by_anchor = {fiber.anchor_id: fiber for fiber in fibers}
    found: set[str] = set()
    for synapse in store.synapses():
        if synapse.type != "contradicts":
            continue
        left = by_anchor.get(synapse.source_id)
        right = by_anchor.get(synapse.target_id)
        if left is not None and right is not None:
            found.update({left.id, right.id})
    return found


def _last_time(store: MemoryStore, current: str | None) -> str:
    for session in reversed(store.sessions()):
        if session.id == current or not session.summary:
            continue
        return session.summary
    return ""
