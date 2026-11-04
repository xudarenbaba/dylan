"""Physical deletion. Decay never deletes; this does."""

from __future__ import annotations

from datetime import timedelta

from dylan.clock import load_time
from dylan.memory.limits import Limits
from dylan.memory.store import MemoryStore


def prunable_synapses(store: MemoryStore, limits: Limits | None = None) -> list[str]:
    limits = limits or Limits()
    now = store.clock.now()
    pinned_neurons = {neuron.id for neuron in store.neurons() if neuron.pinned}
    found: list[str] = []
    for synapse in store.synapses():
        if synapse.source_id in pinned_neurons or synapse.target_id in pinned_neurons:
            continue
        if synapse.weight >= limits.prune_weight:
            continue
        started = load_time(synapse.last_activated_at or synapse.created_at)
        if now - started < timedelta(days=limits.prune_inactive_days):
            continue
        found.append(synapse.id)
    return found


def prune(store: MemoryStore, limits: Limits | None = None) -> int:
    limits = limits or Limits()
    removed = 0
    now = store.clock.now()
    for synapse_id in prunable_synapses(store, limits):
        store.delete_synapse(synapse_id)
        removed += 1
    for fiber in list(store.fibers()):
        if fiber.pinned or fiber.memory_type == "identity":
            continue
        if fiber.state != "soft_deleted" or not fiber.deleted_at:
            continue
        if now - load_time(fiber.deleted_at) < timedelta(days=limits.grace_days):
            continue
        store.delete_fiber(fiber.id)
        removed += 1
    referenced: set[str] = set()
    for synapse in store.synapses():
        referenced.add(synapse.source_id)
        referenced.add(synapse.target_id)
    for fiber in store.fibers():
        referenced.update(fiber.neuron_ids)
    observations = store.conn.execute("SELECT signature FROM sequence_observations")
    for row in observations:
        referenced.update(part for part in str(row["signature"]).split(">") if part)
    for row in store.conn.execute("SELECT neuron_id FROM recall_hits"):
        referenced.add(str(row["neuron_id"]))
    pairs = store.conn.execute("SELECT neuron_a, neuron_b FROM coactivations")
    for row in pairs:
        referenced.add(str(row["neuron_a"]))
        referenced.add(str(row["neuron_b"]))
    for neuron in store.neurons():
        if neuron.pinned or neuron.id in referenced:
            continue
        store.conn.execute("DELETE FROM neurons WHERE id = ?", (neuron.id,))
        removed += 1
    return removed
