"""Promote working fibers that have settled into semantic memory."""

from __future__ import annotations

from dylan.clock import days_between, load_time
from dylan.memory.constants import (
    MATURE_MIN_CONDUCTIVITY,
    MATURE_MIN_DAYS,
    MATURE_MIN_FREQUENCY,
)
from dylan.memory.store import MemoryStore


def run(store: MemoryStore) -> int:
    now = store.clock.now()
    changed = 0
    for fiber in list(store.fibers()):
        if fiber.state != "active" or fiber.stage != "working":
            continue
        age = days_between(load_time(fiber.created_at), now)
        if age < MATURE_MIN_DAYS:
            continue
        if fiber.frequency < MATURE_MIN_FREQUENCY or fiber.conductivity < MATURE_MIN_CONDUCTIVITY:
            continue
        store.save_fiber(fiber.model_copy(update={"stage": "semantic"}))
        changed += 1
    return changed
