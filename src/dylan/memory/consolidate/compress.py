"""Lower compression tiers. Tier 4 only on an explicit compress run."""

from __future__ import annotations

from typing import Protocol

from dylan.memory.compress import demote
from dylan.memory.store import MemoryStore


class TextCompressor(Protocol):
    def summaries(self, text: str) -> tuple[str, str, str] | None: ...


def run(store: MemoryStore, compressor: TextCompressor | None = None) -> int:
    now = store.clock.now()
    changed = 0
    for fiber in list(store.fibers()):
        if fiber.pinned or fiber.memory_type == "identity" or fiber.state != "active":
            continue
        updated = demote(fiber, now, explicit=True)
        if updated.compression_tier == fiber.compression_tier and updated.body == fiber.body:
            continue
        if compressor is not None:
            produced = compressor.summaries(fiber.body or fiber.summary)
            if produced is None:
                continue
            summary, essence, ghost = produced
            updated = updated.model_copy(
                update={"summary": summary, "essence": essence, "ghost": ghost}
            )
        store.save_fiber(updated)
        changed += 1
    return changed
