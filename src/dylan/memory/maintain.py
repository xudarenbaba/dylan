"""Settling time and clearing what has truly gone. Runs at start-up and during sleep."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from dylan.clock import dump_time, load_time
from dylan.memory.constants import (
    ANCHOR_KIND,
    FORGET_STRENGTH,
    FORGET_TRACE_DAYS,
    MERGED_DROP_DAYS,
    PRUNE_LINK_DAYS,
    PRUNE_LINK_WEIGHT,
    SUPPRESS_DROP_DAYS,
)
from dylan.memory.physiology import grown_weight, settle
from dylan.memory.store import MemoryStore


@dataclass
class Upkeep:
    settled: int = 0
    links: int = 0
    memories: int = 0
    nodes: int = 0


def maintain(store: MemoryStore) -> Upkeep:
    """Idempotent: a second call at the same clock changes nothing."""
    result = Upkeep()
    with store.transaction():
        result.settled = settle_all(store)
        result.links, result.memories, result.nodes = prune(store)
    return result


def settle_all(store: MemoryStore) -> int:
    now = store.clock.now()
    changed = 0
    for fiber in store.fibers():
        settled = settle(fiber, now)
        if settled != fiber:
            store.save_fiber(settled)
            changed += 1
    store.set_meta(settled_at=dump_time(now))
    return changed


def prune(store: MemoryStore) -> tuple[int, int, int]:
    now = store.clock.now()
    links = 0
    for synapse in store.synapses():
        if synapse.type != "co_recalled" or synapse.innate:
            continue
        idle = now - load_time(synapse.last_activated_at)
        weak = grown_weight(synapse, now) < PRUNE_LINK_WEIGHT
        if weak and idle >= timedelta(days=PRUNE_LINK_DAYS):
            store.delete_synapse(synapse.id)
            links += 1
    gone: list[str] = []
    for fiber in store.fibers():
        if fiber.memory_type == "innate":
            continue
        changed = now - load_time(fiber.state_changed_at)
        last = load_time(fiber.last_recalled_at or fiber.created_at)
        if fiber.state == "suppressed" and changed >= timedelta(days=SUPPRESS_DROP_DAYS):
            gone.append(fiber.id)
        elif fiber.state == "merged" and changed >= timedelta(days=MERGED_DROP_DAYS):
            gone.append(fiber.id)
        elif (
            fiber.detail_level >= 3
            and fiber.strength < FORGET_STRENGTH
            and now - last >= timedelta(days=FORGET_TRACE_DAYS)
        ):
            gone.append(fiber.id)
    if gone:
        owners = store.synapse_owners()
        dropping = set(gone)
        for synapse in store.synapses():
            holders = owners.get(synapse.id, [])
            if synapse.innate or not holders:
                continue
            if set(holders) <= dropping:
                store.delete_synapse(synapse.id)
        for fiber_id in gone:
            store.delete_fiber(fiber_id)
    nodes = _drop_orphans(store)
    return links, len(gone), nodes


def _drop_orphans(store: MemoryStore) -> int:
    meta = store.meta()
    keep = {meta["user_id"], meta["self_id"]}
    used: set[str] = set()
    for row in store.conn.execute("SELECT neuron_id FROM fiber_neurons"):
        used.add(row["neuron_id"])
    for row in store.conn.execute("SELECT source_id, target_id FROM synapses"):
        used.update((row["source_id"], row["target_id"]))
    for row in store.conn.execute("SELECT anchor_id FROM fibers"):
        used.add(row["anchor_id"])
    removed = 0
    for neuron in store.neurons():
        if neuron.id in keep or neuron.id in used or neuron.innate:
            continue
        if neuron.kind == ANCHOR_KIND:
            continue
        store.delete_neuron(neuron.id)
        removed += 1
    store.conn.execute(
        """
        DELETE FROM coactivations
        WHERE neuron_a NOT IN (SELECT id FROM neurons) OR neuron_b NOT IN (SELECT id FROM neurons)
        """
    )
    return removed
