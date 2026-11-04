"""One insight fiber for three episodes that share the same tags."""

from __future__ import annotations

from collections import defaultdict

from dylan.memory.constants import TRUST_CAP
from dylan.memory.encode import Draft, insert_generated
from dylan.memory.store import MemoryStore


def run(store: MemoryStore) -> int:
    groups: dict[tuple[str, ...], list] = defaultdict(list)
    for fiber in store.fibers():
        if fiber.state != "active" or fiber.memory_type != "episode" or not fiber.tags:
            continue
        groups[tuple(fiber.tags)].append(fiber)
    known = {
        fiber.summary
        for fiber in store.fibers()
        if fiber.memory_type == "insight" and fiber.provenance.source == "consolidation"
    }
    created = 0
    for tags, members in groups.items():
        if len(members) < 3:
            continue
        label = "、".join(tags)
        summary = f"这些经历都关于{label}"
        if summary in known:
            continue
        concept = store.ensure_neuron("concept", label)
        insert_generated(
            store,
            Draft(
                memory_type="insight",
                summary=summary,
                body=summary,
                source="consolidation",
                confidence="medium",
                trust=TRUST_CAP["consolidation"],
                tags=list(tags),
            ),
            [concept.id],
            [],
        )
        known.add(summary)
        created += 1
    return created
