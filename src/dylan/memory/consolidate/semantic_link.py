"""Link anchors when tags overlap and the fibers share no neuron."""

from __future__ import annotations

from dylan.memory.constants import DEFAULT_SYNAPSE_WEIGHT
from dylan.memory.jaccard import jaccard
from dylan.memory.limits import Limits
from dylan.memory.roles import direction_for
from dylan.memory.store import MemoryStore


def run(store: MemoryStore, limits: Limits | None = None) -> int:
    limits = limits or Limits()
    fibers = [fiber for fiber in store.fibers() if fiber.state == "active" and fiber.tags]
    existing = {
        tuple(sorted((synapse.source_id, synapse.target_id)))
        for synapse in store.synapses()
        if synapse.type == "similar_to"
    }
    changed = 0
    for index, left in enumerate(fibers):
        for right in fibers[index + 1 :]:
            if set(left.neuron_ids) & set(right.neuron_ids):
                continue
            if jaccard("".join(left.tags), "".join(right.tags)) < limits.tag_jaccard:
                continue
            key = tuple(sorted((left.anchor_neuron_id, right.anchor_neuron_id)))
            if key in existing or left.anchor_neuron_id == right.anchor_neuron_id:
                continue
            store.add_synapse(
                left.anchor_neuron_id,
                right.anchor_neuron_id,
                "similar_to",
                direction=direction_for("similar_to"),
                base_weight=DEFAULT_SYNAPSE_WEIGHT,
            )
            existing.add(key)
            changed += 1
    return changed
