"""Four health figures and the first matching suggestion."""

from __future__ import annotations

from datetime import timedelta

from dylan.clock import load_time
from dylan.memory.constants import (
    COMPRESS_MAX_CONDUCTIVITY,
    COMPRESS_MIN_AGE_DAYS,
    FRESH_DAYS,
    HABIT_MIN_DAYS,
    MATURE_MIN_CONDUCTIVITY,
    MATURE_MIN_DAYS,
    MATURE_MIN_FREQUENCY,
)
from dylan.memory.limits import Limits
from dylan.memory.prune import prunable_synapses
from dylan.memory.store import MemoryStore


def _mature_ready(store: MemoryStore) -> bool:
    now = store.clock.now()
    for fiber in store.fibers():
        if fiber.stage != "working" or fiber.state != "active":
            continue
        age = (now - load_time(fiber.created_at)).total_seconds() / 86400.0
        if (
            age >= MATURE_MIN_DAYS
            and fiber.frequency >= MATURE_MIN_FREQUENCY
            and fiber.conductivity >= MATURE_MIN_CONDUCTIVITY
        ):
            return True
    return False


def _unresolved_conflicts(store: MemoryStore) -> int:
    synapses = store.synapses()
    resolved: set[tuple[str, str]] = set()
    for synapse in synapses:
        if synapse.type in {"resolved_by", "supersedes"}:
            resolved.add(tuple(sorted((synapse.source_id, synapse.target_id))))
    count = 0
    for synapse in synapses:
        if synapse.type != "contradicts":
            continue
        pair = tuple(sorted((synapse.source_id, synapse.target_id)))
        if pair not in resolved:
            count += 1
    return count


def _habit_ready(store: MemoryStore) -> bool:
    workflow_paths = {
        ">".join(fiber.neuron_ids)
        for fiber in store.fibers()
        if fiber.memory_type == "workflow"
    }
    for signature in store.sequence_signatures():
        if signature in workflow_paths:
            continue
        if len(store.sequence_days(signature)) >= HABIT_MIN_DAYS:
            return True
    return False


def _compress_ready(store: MemoryStore) -> bool:
    now = store.clock.now()
    for fiber in store.fibers():
        if fiber.conductivity >= COMPRESS_MAX_CONDUCTIVITY:
            continue
        conducted = load_time(fiber.last_conducted_at or fiber.created_at)
        if now - conducted >= timedelta(days=COMPRESS_MIN_AGE_DAYS):
            return True
    return False


def report(store: MemoryStore, limits: Limits | None = None) -> dict[str, float | str]:
    limits = limits or Limits()
    fibers = [fiber for fiber in store.fibers() if fiber.memory_type != "identity"]
    semantic = [fiber for fiber in fibers if fiber.stage == "semantic"]
    ratio = (len(semantic) / len(fibers)) if fibers else 0.0
    neurons = store.neurons()
    if neurons:
        degree = (2 * len(store.synapses())) / len(neurons)
    else:
        degree = 0.0
    now = store.clock.now()
    all_fibers = store.fibers()
    if all_fibers:
        fresh = 0
        for fiber in all_fibers:
            conducted = load_time(fiber.last_conducted_at or fiber.created_at)
            if now - conducted <= timedelta(days=FRESH_DAYS):
                fresh += 1
        freshness = fresh / len(all_fibers)
    else:
        freshness = 0.0
    conflicts = _unresolved_conflicts(store)
    if prunable_synapses(store, limits):
        suggestion = "prune"
    elif _mature_ready(store):
        suggestion = "mature"
    elif conflicts >= 1:
        suggestion = "先处理冲突"
    elif _habit_ready(store):
        suggestion = "learn_habits"
    elif _compress_ready(store):
        suggestion = "compress"
    else:
        suggestion = "无需巩固"
    return {
        "成熟比例": ratio,
        "连通": degree,
        "新鲜": freshness,
        "冲突": float(conflicts),
        "建议": suggestion,
    }
