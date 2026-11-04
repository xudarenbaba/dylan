"""Merge fibers whose neuron sets overlap."""

from __future__ import annotations

from dylan.memory.limits import Limits
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
        left_ids = set(left.neuron_ids)
        for right in fibers[index + 1 :]:
            if right.id in removed:
                continue
            right_ids = set(right.neuron_ids)
            if _jaccard(left_ids, right_ids) < limits.merge_jaccard:
                continue
            if left.conductivity >= right.conductivity:
                keeper, other = left, right
            else:
                keeper, other = right, left
            neuron_ids = list(keeper.neuron_ids)
            for neuron_id in other.neuron_ids:
                if neuron_id not in neuron_ids:
                    neuron_ids.append(neuron_id)
            synapse_ids = list(dict.fromkeys([*keeper.synapse_ids, *other.synapse_ids]))
            store.replace_fiber_members(keeper.id, neuron_ids, synapse_ids)
            fresh = store.fiber(keeper.id)
            if fresh is not None:
                store.save_fiber(
                    fresh.model_copy(
                        update={
                            "rehearsal_count": keeper.rehearsal_count + other.rehearsal_count,
                            "frequency": keeper.frequency + other.frequency,
                        }
                    )
                )
            store.delete_fiber(other.id)
            removed.add(other.id)
            left = store.fiber(keeper.id) or keeper
            changed += 1
    return changed


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)
