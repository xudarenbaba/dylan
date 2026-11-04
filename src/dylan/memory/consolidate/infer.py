"""Add a related_to edge after repeated co-activation."""

from __future__ import annotations

from dylan.memory.constants import INFER_MIN_COUNT, INFER_WEIGHT, LATERAL_TYPES
from dylan.memory.roles import direction_for
from dylan.memory.store import MemoryStore


def run(store: MemoryStore) -> int:
    changed = 0
    laterals = {
        tuple(sorted((synapse.source_id, synapse.target_id)))
        for synapse in store.synapses()
        if synapse.type in LATERAL_TYPES
    }
    for left, right, count in store.coactivations():
        if count < INFER_MIN_COUNT:
            continue
        if tuple(sorted((left, right))) in laterals:
            continue
        store.add_synapse(
            left,
            right,
            "related_to",
            direction=direction_for("related_to"),
            base_weight=INFER_WEIGHT,
        )
        laterals.add(tuple(sorted((left, right))))
        changed += 1
    return changed
