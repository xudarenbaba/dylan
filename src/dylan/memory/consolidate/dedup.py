"""Collapse fibers whose summaries overlap at the dedup threshold."""

from __future__ import annotations

from dylan.memory.jaccard import jaccard
from dylan.memory.lifecycle import soft_delete
from dylan.memory.limits import Limits
from dylan.memory.model import Fiber
from dylan.memory.stage import maybe_working
from dylan.memory.store import MemoryStore


def run(store: MemoryStore, limits: Limits | None = None) -> int:
    limits = limits or Limits()
    fibers = [
        fiber
        for fiber in store.fibers()
        if fiber.state == "active" and not fiber.pinned and fiber.memory_type != "identity"
    ]
    removed: set[str] = set()
    changed = 0
    for index, left in enumerate(fibers):
        if left.id in removed:
            continue
        for right in fibers[index + 1 :]:
            if right.id in removed or left.id in removed:
                continue
            if jaccard(left.summary, right.summary) < limits.dedup_jaccard:
                continue
            if left.conductivity >= right.conductivity:
                keeper, other = left, right
            else:
                keeper, other = right, left
            merged = _combine(keeper, other)
            store.save_fiber(merged)
            soft_delete(store, other)
            removed.add(other.id)
            changed += 1
            if other.id == left.id:
                break
            left = merged
    return changed


def _combine(keeper: Fiber, other: Fiber) -> Fiber:
    dates = list(dict.fromkeys([*keeper.recall_dates, *other.recall_dates]))
    merged = keeper.model_copy(
        update={
            "rehearsal_count": keeper.rehearsal_count + other.rehearsal_count,
            "frequency": keeper.frequency + other.frequency,
            "recall_dates": dates,
        }
    )
    return maybe_working(merged)
