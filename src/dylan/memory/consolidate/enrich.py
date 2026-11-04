"""Fill tags and time only when the original text already contains them."""

from __future__ import annotations

from datetime import timedelta

from dylan.clock import dump_time
from dylan.memory.anchors import query_dates
from dylan.memory.lexicon_zh import find_time_words
from dylan.memory.store import MemoryStore


def run(store: MemoryStore) -> int:
    changed = 0
    for fiber in list(store.fibers()):
        if fiber.state != "active":
            continue
        text = fiber.body or fiber.summary
        updates: dict[str, object] = {}
        if not fiber.tags:
            words = find_time_words(text)
            if words:
                store.set_tags(fiber.id, words)
                updates["tags"] = words
        if not fiber.time_start:
            dates = query_dates(text)
            if dates:
                start = dates[0]
                end = dates[-1] + timedelta(days=1)
                updates["time_start"] = dump_time(start)
                updates["time_end"] = dump_time(end)
        if not updates:
            continue
        current = store.fiber(fiber.id)
        if current is None:
            continue
        store.save_fiber(current.model_copy(update=updates))
        changed += 1
    return changed
