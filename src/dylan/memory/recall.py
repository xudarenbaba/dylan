"""Reflex activation, co-activation, causal adjustment and scoring."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

from dylan.clock import days_between, dump_time, load_time
from dylan.memory.anchors import overlaps, query_dates, select_anchors, time_window
from dylan.memory.compress import promote_tier
from dylan.memory.constants import (
    ANCHOR_CAP,
    BOOST,
    CLEAR_SCORE,
    COACTIVATION_BONUS,
    CONDUCTIVITY_BUMP,
    PRIORITY_BASE,
    PRIORITY_SCALE,
    SCORE_FLOOR,
    STAGE_FACTOR,
    WEAKEN,
)
from dylan.memory.hebbian import reinforce
from dylan.memory.lifecycle import expire_due
from dylan.memory.limits import Limits
from dylan.memory.model import Fiber, Neuron, Synapse
from dylan.memory.roles import (
    can_traverse,
    direction_for,
    is_reinforce,
    is_supersede_source,
    is_supersede_target,
    is_weaken,
)
from dylan.memory.stage import maybe_working
from dylan.memory.store import MemoryStore, day_key


@dataclass
class Hit:
    fiber: Fiber
    score: float
    certainty: str
    path: list[str]


@dataclass
class Recall:
    depth: int
    hits: list[Hit] = field(default_factory=list)
    conflicts: list[dict[str, str]] = field(default_factory=list)
    certainty: str = "none"
    activation: dict[str, float] = field(default_factory=dict)
    traversed_ids: list[str] = field(default_factory=list)
    contributors: dict[str, set[str]] = field(default_factory=dict)
    persisted: bool = False

    @property
    def intent(self) -> str:
        if self.conflicts:
            return "state_conflict"
        if self.certainty == "none":
            return "unknown"
        attitudes = {hit.certainty for hit in self.hits}
        if attitudes & {"clear", "faint"}:
            return "use_memory"
        if attitudes == {"inferred"}:
            return "confirm"
        return "unknown"


def recall(
    store: MemoryStore,
    query: str,
    *,
    depth: int,
    max_hops: int,
    window_days: int,
    limit: int | None = None,
    limits: Limits | None = None,
    persist: bool = True,
) -> Recall:
    limits = limits or Limits()
    chosen_limit = limits.recall_limit if limit is None else limit
    if persist:
        with store.transaction():
            expire_due(store)
            result = _compute(
                store,
                query,
                depth=depth,
                max_hops=max_hops,
                window_days=window_days,
                limit=chosen_limit,
                limits=limits,
            )
            persist_recall(store, result)
            return result
    return _compute(
        store,
        query,
        depth=depth,
        max_hops=max_hops,
        window_days=window_days,
        limit=chosen_limit,
        limits=limits,
    )


def persist_recall(store: MemoryStore, result: Recall) -> None:
    """Write reinforcement for one recall. Safe to call once after a read-only pass."""
    if result.persisted:
        return
    today = day_key(dump_time(store.clock.now()))
    now = dump_time(store.clock.now())
    concepts: list[str] = []
    neurons = {neuron.id: neuron for neuron in store.neurons()}
    for hit in result.hits:
        fiber = promote_tier(hit.fiber)
        dates = list(fiber.recall_dates)
        if today not in dates:
            dates.append(today)
        fiber = fiber.model_copy(
            update={
                "conductivity": min(1.0, fiber.conductivity + CONDUCTIVITY_BUMP),
                "base_conductivity": min(1.0, fiber.base_conductivity + CONDUCTIVITY_BUMP),
                "frequency": fiber.frequency + 1,
                "last_conducted_at": now,
                "last_activated_at": now,
                "recall_dates": dates,
            }
        )
        fiber = maybe_working(fiber)
        store.save_fiber(fiber)
        hit.fiber = fiber
        for neuron_id in fiber.neuron_ids:
            neuron = neurons.get(neuron_id)
            if neuron is not None and neuron.kind == "concept":
                concepts.append(neuron_id)
    seen: set[str] = set()
    by_id = {synapse.id: synapse for synapse in store.synapses()}
    for synapse_id in result.traversed_ids:
        if synapse_id in seen:
            continue
        seen.add(synapse_id)
        synapse = by_id.get(synapse_id)
        if synapse is None:
            continue
        reinforce(
            store,
            synapse,
            result.activation.get(synapse.source_id),
            result.activation.get(synapse.target_id),
        )
    _bind_coactivation(store, result.contributors, result.activation)
    if concepts:
        store.add_recall_run(concepts)
    result.persisted = True


def _compute(
    store: MemoryStore,
    query: str,
    *,
    depth: int,
    max_hops: int,
    window_days: int,
    limit: int,
    limits: Limits,
) -> Recall:
    threshold = limits.activation_threshold
    rate = limits.decay_rate
    neurons = {neuron.id: neuron for neuron in store.neurons()}
    synapses = store.synapses()
    fibers = store.fibers()
    synapse_types = {synapse.id: synapse.type for synapse in synapses}
    workflow_ids = {
        neuron_id
        for fiber in fibers
        if fiber.memory_type == "workflow"
        for neuron_id in fiber.neuron_ids
    }
    anchors = select_anchors(list(neurons.values()), query, workflow_ids)
    activation: dict[str, float] = {}
    contributors: dict[str, set[str]] = defaultdict(set)
    parents: dict[tuple[str, str], tuple[str, str]] = {}
    traversed: list[str] = []
    by_anchor: dict[str, dict[str, float]] = {}
    outgoing: dict[str, list[tuple[Synapse, str]]] = defaultdict(list)
    for synapse in synapses:
        outgoing[synapse.source_id].append((synapse, synapse.target_id))
        if synapse.direction == "bi":
            outgoing[synapse.target_id].append((synapse, synapse.source_id))

    for anchor_id, initial in anchors:
        local = {anchor_id: initial}
        queue: deque[tuple[str, int]] = deque([(anchor_id, 0)])
        while queue:
            node_id, hop = queue.popleft()
            if hop >= max_hops:
                continue
            current = local[node_id]
            for synapse, nxt in outgoing.get(node_id, []):
                if not can_traverse(synapse.type, depth):
                    continue
                cond = _conductivity(synapse, fibers)
                factor = _time_factor(neurons.get(node_id), neurons.get(nxt), window_days)
                nxt_act = current * (1.0 - rate) * synapse.weight * cond * factor
                if nxt_act < threshold:
                    continue
                if nxt_act <= local.get(nxt, 0.0):
                    continue
                local[nxt] = nxt_act
                parents[(anchor_id, nxt)] = (node_id, synapse.type)
                traversed.append(synapse.id)
                queue.append((nxt, hop + 1))
        by_anchor[anchor_id] = local
        for node_id, value in local.items():
            activation[node_id] = max(activation.get(node_id, 0.0), value)
            contributors[node_id].add(anchor_id)

    for node_id, sources in contributors.items():
        if len(sources) >= 2:
            activation[node_id] = min(1.0, activation[node_id] + COACTIVATION_BONUS * len(sources))

    if window_days > 0:
        for moment in query_dates(query):
            start, end = time_window(moment, window_days)
            for fiber in fibers:
                if fiber.state != "active" or not overlaps(fiber, start, end):
                    continue
                anchor = fiber.anchor_neuron_id
                activation[anchor] = max(activation.get(anchor, 0.0), ANCHOR_CAP["time"])

    conflicts: list[dict[str, str]] = []
    for synapse in synapses:
        source_act = activation.get(synapse.source_id, 0.0)
        if source_act < threshold:
            continue
        if is_weaken(synapse.type):
            activation[synapse.target_id] = activation.get(synapse.target_id, 0.0) * WEAKEN
            conflicts.extend(_conflict_pairs(fibers, synapse, activation, threshold))
        elif is_reinforce(synapse.type):
            activation[synapse.target_id] = min(1.0, activation.get(synapse.target_id, 0.0) * BOOST)
        elif is_supersede_source(synapse.type):
            activation[synapse.source_id] = min(1.0, source_act * BOOST)
            activation[synapse.target_id] = activation.get(synapse.target_id, 0.0) * WEAKEN
        elif is_supersede_target(synapse.type):
            activation[synapse.target_id] = min(1.0, activation.get(synapse.target_id, 0.0) * BOOST)
            activation[synapse.source_id] = source_act * WEAKEN

    ranked: list[Hit] = []
    for fiber in fibers:
        if not _eligible(fiber, query):
            continue
        hits = [
            activation.get(neuron_id, 0.0)
            for neuron_id in fiber.neuron_ids
            if activation.get(neuron_id, 0.0) >= threshold
        ]
        if not hits:
            continue
        score = (
            fiber.conductivity
            * (sum(hits) / len(hits))
            * STAGE_FACTOR.get(fiber.stage, 1.0)
            * (PRIORITY_BASE + fiber.priority / PRIORITY_SCALE)
        )
        if score < SCORE_FLOOR:
            continue
        path = _path(fiber, by_anchor, parents, threshold)
        ranked.append(Hit(fiber, score, _certainty(fiber, score), path))
    ranked.sort(
        key=lambda hit: (hit.score, _depth2_bias(hit.fiber, depth, synapse_types)),
        reverse=True,
    )
    selected = ranked[:limit]
    result = Recall(
        depth=depth,
        hits=selected,
        conflicts=_unique_conflicts(conflicts),
        activation=dict(activation),
        traversed_ids=traversed,
        contributors={key: set(value) for key, value in contributors.items()},
    )
    if not selected:
        result.certainty = "none"
    else:
        result.certainty = _strictest([hit.certainty for hit in selected])
    return result


def _conductivity(synapse: Synapse, fibers: list[Fiber]) -> float:
    values = [fiber.conductivity for fiber in fibers if synapse.id in fiber.synapse_ids]
    return max(values) if values else 1.0


def _stamp(content: str) -> str:
    if "T" in content:
        return content
    return f"{content[:10]}T00:00:00Z"


def _time_factor(left: Neuron | None, right: Neuron | None, window_days: int) -> float:
    if window_days <= 0 or left is None or right is None:
        return 1.0
    if left.kind != "time" or right.kind != "time":
        return 1.0
    try:
        start = load_time(_stamp(left.content))
        end = load_time(_stamp(right.content))
    except ValueError:
        return 1.0
    return math.exp(-abs(days_between(start, end)) / window_days)


def _certainty(fiber: Fiber, score: float) -> str:
    source = fiber.provenance.source
    confidence = fiber.provenance.confidence
    if source in {"dream", "consolidation", "ai_inference"} or confidence in {"low", "inferred"}:
        return "inferred"
    if score >= CLEAR_SCORE and (
        source == "user_input" or (fiber.pinned and fiber.memory_type == "identity")
    ):
        return "clear"
    if score >= SCORE_FLOOR:
        return "faint"
    return "none"


def _named_cold(fiber: Fiber, query: str) -> bool:
    from dylan.memory.constants import ANCHOR_JACCARD
    from dylan.memory.jaccard import jaccard

    if any(word in query for word in ("更早", "以前", "老的")):
        return True
    anchor = fiber.summary
    return jaccard(anchor, query) >= ANCHOR_JACCARD or bool(anchor and anchor in query)


def _eligible(fiber: Fiber, query: str) -> bool:
    if fiber.state != "active":
        return False
    if fiber.tier == "cold" and not _named_cold(fiber, query):
        return False
    return True


def _depth2_bias(fiber: Fiber, depth: int, synapse_types: dict[str, str]) -> int:
    if depth != 2:
        return 0
    if fiber.memory_type == "workflow":
        return 1
    for synapse_id in fiber.synapse_ids:
        if synapse_types.get(synapse_id) in {"before", "after"}:
            return 1
    return 0


def _walk(
    anchor_id: str,
    target: str,
    parents: dict[tuple[str, str], tuple[str, str]],
) -> list[str]:
    if target == anchor_id:
        return [anchor_id]
    chain = [target]
    cursor = target
    guard = 0
    while cursor != anchor_id and guard < 12:
        parent = parents.get((anchor_id, cursor))
        if parent is None:
            return []
        previous, synapse_type = parent
        chain.append(synapse_type)
        chain.append(previous)
        cursor = previous
        guard += 1
    if cursor != anchor_id:
        return []
    chain.reverse()
    return chain


def _path(
    fiber: Fiber,
    by_anchor: dict[str, dict[str, float]],
    parents: dict[tuple[str, str], tuple[str, str]],
    threshold: float,
) -> list[str]:
    best: list[str] = []
    for neuron_id in fiber.neuron_ids:
        for anchor_id, local in by_anchor.items():
            if local.get(neuron_id, 0.0) < threshold and neuron_id != anchor_id:
                continue
            chain = _walk(anchor_id, neuron_id, parents)
            if len(chain) > len(best):
                best = chain
    return best or [fiber.anchor_neuron_id]


def _conflict_pairs(
    fibers: list[Fiber],
    synapse: Synapse,
    activation: dict[str, float],
    threshold: float,
) -> list[dict[str, str]]:
    def live(fiber: Fiber) -> bool:
        return any(activation.get(neuron_id, 0.0) >= threshold for neuron_id in fiber.neuron_ids)

    left = [fiber for fiber in fibers if synapse.source_id in fiber.neuron_ids and live(fiber)]
    right = [fiber for fiber in fibers if synapse.target_id in fiber.neuron_ids and live(fiber)]
    pairs: list[dict[str, str]] = []
    for one in left:
        for two in right:
            if one.id == two.id:
                continue
            pairs.append(
                {
                    "left_id": one.id,
                    "right_id": two.id,
                    "left": one.summary,
                    "right": two.summary,
                }
            )
    return pairs


def _unique_conflicts(conflicts: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in conflicts:
        key = tuple(sorted((item["left_id"], item["right_id"])))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _strictest(attitudes: list[str]) -> str:
    order = {"inferred": 0, "faint": 1, "clear": 2, "none": -1}
    chosen = "clear"
    for attitude in attitudes:
        if order[attitude] < order[chosen]:
            chosen = attitude
    return chosen


def _bind_coactivation(
    store: MemoryStore,
    contributors: dict[str, set[str]],
    activation: dict[str, float],
) -> None:
    from dylan.memory.constants import DEFAULT_SYNAPSE_WEIGHT

    pairs: set[tuple[str, str]] = set()
    for sources in contributors.values():
        ids = sorted(sources)
        if len(ids) < 2:
            continue
        for index, left in enumerate(ids):
            for right in ids[index + 1 :]:
                pairs.add((left, right))
    for left, right in pairs:
        store.bump_coactivation(left, right)
        matched = [
            synapse
            for synapse in store.synapses()
            if synapse.type == "co_occurs"
            and {synapse.source_id, synapse.target_id} == {left, right}
        ]
        if matched:
            for synapse in matched:
                reinforce(store, synapse, activation.get(left, 1.0), activation.get(right, 1.0))
            continue
        created = store.add_synapse(
            left,
            right,
            "co_occurs",
            direction=direction_for("co_occurs"),
            base_weight=DEFAULT_SYNAPSE_WEIGHT,
        )
        reinforce(store, created, activation.get(left, 1.0), activation.get(right, 1.0))
