"""Turn a repeated ordered signature into one workflow fiber."""

from __future__ import annotations

from dylan.memory.constants import (
    DEFAULT_SYNAPSE_WEIGHT,
    HABIT_MIN_DAYS,
    TRUST_CAP,
)
from dylan.memory.encode import Draft, insert_generated
from dylan.memory.hebbian import reinforce
from dylan.memory.roles import direction_for, inverse_type
from dylan.memory.store import MemoryStore


def run(store: MemoryStore) -> int:
    existing = {
        ">".join(fiber.neuron_ids)
        for fiber in store.fibers()
        if fiber.memory_type == "workflow" and fiber.state == "active"
    }
    created = 0
    for signature in store.sequence_signatures():
        if signature in existing:
            continue
        if len(store.sequence_days(signature)) < HABIT_MIN_DAYS:
            continue
        neuron_ids = [part for part in signature.split(">") if part]
        if len(neuron_ids) < 2:
            continue
        synapse_ids = _strengthen(store, neuron_ids)
        labels = []
        for neuron_id in neuron_ids:
            neuron = store.neuron(neuron_id)
            labels.append(neuron.content if neuron is not None else neuron_id)
        summary = "然后".join(labels)
        insert_generated(
            store,
            Draft(
                memory_type="workflow",
                summary=summary,
                body=summary,
                source="consolidation",
                confidence="medium",
                trust=TRUST_CAP["consolidation"],
                tags=labels,
            ),
            neuron_ids,
            synapse_ids,
        )
        existing.add(signature)
        created += 1
    return created


def strengthen_online(store: MemoryStore, neuron_ids: list[str]) -> None:
    """Reinforce before/after for an order already seen in this session. No workflow."""
    if len(neuron_ids) < 2:
        return
    _strengthen(store, neuron_ids)


def _strengthen(store: MemoryStore, neuron_ids: list[str]) -> list[str]:
    synapse_ids: list[str] = []
    for left, right in zip(neuron_ids, neuron_ids[1:]):
        if left == right:
            continue
        created = store.add_synapse(
            left,
            right,
            "before",
            direction=direction_for("before"),
            base_weight=DEFAULT_SYNAPSE_WEIGHT,
        )
        reinforce(store, created, 1.0, 1.0)
        synapse_ids.append(created.id)
        inverse = inverse_type("before")
        if inverse is None:
            continue
        back = store.add_synapse(
            right,
            left,
            inverse,
            direction=direction_for(inverse),
            base_weight=DEFAULT_SYNAPSE_WEIGHT,
        )
        reinforce(store, back, 1.0, 1.0)
        synapse_ids.append(back.id)
    return synapse_ids
