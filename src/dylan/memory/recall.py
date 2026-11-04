"""Spreading recall. Names, aliases, cues and dates light nodes; links carry the rest."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from itertools import combinations

from dylan.clock import day_bounds, load_time, mentioned_days
from dylan.memory.constants import (
    CARRY_WEIGHT,
    COACTIVATION_MIN,
    CONTEXT_WEIGHTS,
    CUE_WEIGHT,
    DATE_WEIGHT,
    GROWN_LINK_WEIGHT,
    HUB_DEGREE,
    NODE_WEIGHT,
    RECALL_FLOOR,
    RECALL_LIMIT,
    RECALLABLE_STATES,
    SHOWN_BUMP,
    SPREAD_DECAY,
    SPREAD_FLOOR,
    SPREAD_MAX_HOPS,
    SUPERSEDED_CONDUCT,
)
from dylan.memory.model import Fiber
from dylan.memory.physiology import clarity, hebbian, link_weight, strengthen
from dylan.memory.store import MemoryStore
from dylan.memory.text import windows

_NO_SPREAD = frozenset({"happened_on", "felt"})
_STRENGTH_FLOOR = 0.3


@dataclass
class Hit:
    fiber: Fiber
    score: float
    clarity: str
    partner: str | None = None


@dataclass
class Recall:
    hits: list[Hit] = field(default_factory=list)
    activation: dict[str, float] = field(default_factory=dict)
    lit: list[str] = field(default_factory=list)


def recall(
    store: MemoryStore,
    texts: list[str],
    tz: tzinfo,
    *,
    carry: list[str] | None = None,
    exclude: set[str] | None = None,
    limit: int = RECALL_LIMIT,
) -> Recall:
    """Read-only. Nothing changes until persist_recall."""
    now = store.clock.now()
    fibers = {fiber.id: fiber for fiber in store.fibers(RECALLABLE_STATES)}
    by_anchor = {fiber.anchor_id: fiber for fiber in fibers.values()}
    seeds: dict[str, float] = defaultdict(float)
    names = store.name_index()
    cues = store.cue_index()
    for index, text in enumerate(texts[: len(CONTEXT_WEIGHTS)]):
        weight = CONTEXT_WEIGHTS[index]
        terms = windows(text)
        for term in terms:
            for node_id in names.get(term, ()):
                seeds[node_id] = max(seeds[node_id], NODE_WEIGHT * weight)
            for fiber_id in cues.get(term, ()):
                fiber = fibers.get(fiber_id)
                if fiber is not None:
                    seeds[fiber.anchor_id] = max(seeds[fiber.anchor_id], CUE_WEIGHT * weight)
        for day in mentioned_days(text, now, tz):
            for fiber in _on_day(fibers.values(), day, tz):
                seeds[fiber.anchor_id] = max(seeds[fiber.anchor_id], DATE_WEIGHT * weight)
    for fiber_id in carry or []:
        fiber = fibers.get(fiber_id)
        if fiber is not None:
            seeds[fiber.anchor_id] = max(seeds[fiber.anchor_id], CARRY_WEIGHT)
    activation = _spread(store, dict(seeds), by_anchor, now)
    conflicts, partners = _relations(store, fibers, by_anchor)
    blocked = exclude or set()
    ranked: list[Hit] = []
    for fiber in fibers.values():
        if fiber.id in blocked or fiber.memory_type == "innate":
            continue
        level = activation.get(fiber.anchor_id, 0.0)
        if level < RECALL_FLOOR:
            continue
        factor = _STRENGTH_FLOOR + (1.0 - _STRENGTH_FLOOR) * fiber.strength
        score = level * factor * (0.75 + fiber.importance / 20.0)
        if fiber.state == "superseded":
            score *= SUPERSEDED_CONDUCT
        hit = Hit(fiber, score, clarity(fiber, conflicted=fiber.id in conflicts))
        hit.partner = partners.get(fiber.id)
        ranked.append(hit)
    ranked.sort(key=lambda hit: hit.score, reverse=True)
    chosen = _with_partners(ranked, limit, fibers, blocked)
    lit = [node for node, value in activation.items() if value >= RECALL_FLOOR]
    return Recall(hits=chosen, activation=activation, lit=lit)


def persist_recall(store: MemoryStore, result: Recall, tz: tzinfo) -> None:
    """Being brought to mind strengthens a memory a little and grows co-recall links."""
    now = store.clock.now()
    for hit in result.hits:
        current = store.fiber(hit.fiber.id)
        if current is None:
            continue
        store.save_fiber(strengthen(current, now, SHOWN_BUMP, tz, count=False))
    anchors = [hit.fiber.anchor_id for hit in result.hits]
    for left, right in combinations(sorted(set(anchors)), 2):
        count = store.bump_coactivation(left, right)
        existing = store.synapse_between(left, right, "co_recalled")
        if existing is not None:
            store.save_synapse(hebbian(existing, now))
        elif count >= COACTIVATION_MIN:
            store.add_synapse(left, right, "co_recalled", base_weight=GROWN_LINK_WEIGHT)


def _spread(
    store: MemoryStore,
    seeds: dict[str, float],
    by_anchor: dict[str, Fiber],
    now: datetime,
) -> dict[str, float]:
    """He and she are part of nearly every memory, so they receive activation but never relay it."""
    meta = store.meta()
    sinks = {meta["user_id"], meta["self_id"]}
    edges: dict[str, list[tuple[str, float]]] = defaultdict(list)
    degree: dict[str, int] = defaultdict(int)
    for synapse in store.synapses():
        if synapse.type in _NO_SPREAD:
            continue
        weight = link_weight(synapse, now)
        ends = ((synapse.source_id, synapse.target_id), (synapse.target_id, synapse.source_id))
        for node, other in ends:
            fiber = by_anchor.get(other)
            if fiber is not None and fiber.state == "superseded":
                edges[node].append((other, weight * SUPERSEDED_CONDUCT))
            else:
                edges[node].append((other, weight))
            degree[node] += 1
    activation = dict(seeds)
    queue: deque[tuple[str, int]] = deque((node, 0) for node in seeds)
    while queue:
        node, hops = queue.popleft()
        if hops >= SPREAD_MAX_HOPS or node in sinks:
            continue
        current = activation.get(node, 0.0)
        damping = 1.0 if degree[node] <= HUB_DEGREE else (HUB_DEGREE / degree[node]) ** 0.5
        for other, weight in edges.get(node, ()):
            value = current * (1.0 - SPREAD_DECAY) * weight * damping
            if value < SPREAD_FLOOR or value <= activation.get(other, 0.0):
                continue
            activation[other] = value
            queue.append((other, hops + 1))
    return activation


def _relations(
    store: MemoryStore, fibers: dict[str, Fiber], by_anchor: dict[str, Fiber]
) -> tuple[set[str], dict[str, str]]:
    conflicts: set[str] = set()
    partners: dict[str, str] = {}
    for synapse in store.synapses():
        if synapse.type not in {"contradicts", "supersedes"}:
            continue
        left = by_anchor.get(synapse.source_id)
        right = by_anchor.get(synapse.target_id)
        if left is None or right is None:
            continue
        if synapse.type == "contradicts":
            if left.state == "active" and right.state == "active":
                conflicts.update({left.id, right.id})
                partners.setdefault(left.id, right.id)
                partners.setdefault(right.id, left.id)
        else:
            partners.setdefault(left.id, right.id)
            partners.setdefault(right.id, left.id)
    return conflicts, partners


def _with_partners(
    ranked: list[Hit], limit: int, fibers: dict[str, Fiber], blocked: set[str]
) -> list[Hit]:
    """A memory that was replaced or contradicted comes to mind with its counterpart."""
    chosen: list[Hit] = []
    seen: set[str] = set()
    by_id = {hit.fiber.id: hit for hit in ranked}
    for hit in ranked:
        if len(chosen) >= limit:
            break
        if hit.fiber.id in seen:
            continue
        chosen.append(hit)
        seen.add(hit.fiber.id)
        partner_id = hit.partner
        if partner_id is None or partner_id in seen or partner_id in blocked:
            continue
        partner = by_id.get(partner_id)
        if partner is None and partner_id in fibers:
            fiber = fibers[partner_id]
            seen_as = clarity(fiber, conflicted=hit.clarity == "conflict")
            partner = Hit(fiber, hit.score * 0.5, seen_as)
        if partner is not None and len(chosen) < limit + 1:
            chosen.append(partner)
            seen.add(partner_id)
    return chosen


def _on_day(fibers: object, day: str, tz: tzinfo) -> list[Fiber]:
    bounds = day_bounds(day, tz)
    if bounds is None:
        return []
    start, end = bounds
    found: list[Fiber] = []
    for fiber in fibers:  # type: ignore[attr-defined]
        moments: list[tuple[datetime, datetime]] = []
        if fiber.occurred_start:
            began = load_time(fiber.occurred_start)
            moments.append((began, load_time(fiber.occurred_end) if fiber.occurred_end else began))
        if fiber.due_at:
            due = load_time(fiber.due_at)
            moments.append((due, due))
        if any(left < end and right >= start for left, right in moments):
            found.append(fiber)
    return found
