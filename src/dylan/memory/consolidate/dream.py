"""Bridge two concepts that alternate in recall and share no path."""

from __future__ import annotations

from collections import deque

from dylan.memory.constants import (
    DEFAULT_SYNAPSE_WEIGHT,
    DREAM_LIMIT,
    PASSIVE_TYPES,
    TRUST_CAP,
)
from dylan.memory.encode import Draft, insert_generated
from dylan.memory.roles import direction_for
from dylan.memory.store import MemoryStore


def run(store: MemoryStore) -> int:
    concepts = [
        neuron
        for neuron in store.neurons()
        if neuron.kind == "concept" and neuron.state == "active"
    ]
    hits = store.recall_hit_sets()
    if len(concepts) < 2 or not hits:
        return 0
    outgoing = _outgoing(store)
    ranked: list[tuple[int, str, str]] = []
    for index, left in enumerate(concepts):
        for right in concepts[index + 1 :]:
            linked = _reachable(left.id, right.id, outgoing) or _reachable(
                right.id, left.id, outgoing
            )
            if linked:
                continue
            only_left = sum(1 for item in hits if left.id in item and right.id not in item)
            only_right = sum(1 for item in hits if right.id in item and left.id not in item)
            if only_left < 2 or only_right < 2:
                continue
            mentions = sum(left.id in item for item in hits)
            mentions += sum(right.id in item for item in hits)
            ranked.append((mentions, left.id, right.id))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    created = 0
    for _, left_id, right_id in ranked[:DREAM_LIMIT]:
        left = store.neuron(left_id)
        right = store.neuron(right_id)
        if left is None or right is None:
            continue
        synapse = store.add_synapse(
            left_id,
            right_id,
            "related_to",
            direction=direction_for("related_to"),
            base_weight=DEFAULT_SYNAPSE_WEIGHT,
        )
        summary = f"梦到{left.content}与{right.content}有关"
        insert_generated(
            store,
            Draft(
                memory_type="insight",
                summary=summary,
                body=summary,
                source="dream",
                confidence="inferred",
                trust=TRUST_CAP["dream"],
            ),
            [left_id, right_id],
            [synapse.id],
        )
        created += 1
    return created


def _outgoing(store: MemoryStore) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for synapse in store.synapses():
        if synapse.type in PASSIVE_TYPES:
            continue
        graph.setdefault(synapse.source_id, []).append(synapse.target_id)
        if synapse.direction == "bi":
            graph.setdefault(synapse.target_id, []).append(synapse.source_id)
    return graph


def _reachable(start: str, goal: str, outgoing: dict[str, list[str]]) -> bool:
    seen = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, hop = queue.popleft()
        if hop >= 6:
            continue
        for nxt in outgoing.get(node, []):
            if nxt == goal:
                return True
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, hop + 1))
    return False
