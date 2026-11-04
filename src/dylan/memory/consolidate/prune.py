"""Physical prune used by the consolidation runner."""

from __future__ import annotations

from dylan.memory.limits import Limits
from dylan.memory.prune import prune
from dylan.memory.store import MemoryStore


def run(store: MemoryStore, limits: Limits | None = None) -> int:
    return prune(store, limits)
