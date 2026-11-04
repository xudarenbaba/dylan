"""Load one brain through a read-only connection for the memory page."""

from __future__ import annotations

from datetime import tzinfo
from pathlib import Path

from dylan.clock import Clock, SystemClock
from dylan.memory.constants import (
    CLARITY,
    MEMORY_TYPES,
    NODE_KINDS,
    RELATIONS,
    SOURCES,
    STAGES,
    STATES,
)
from dylan.memory.physiology import clarity, link_weight
from dylan.memory.render import content
from dylan.memory.store import MemoryStore


def graph_payload(path: Path, tz: tzinfo, clock: Clock | None = None) -> dict[str, object]:
    store = MemoryStore.open_readonly(path, clock or SystemClock())
    try:
        now = store.clock.now()
        meta = store.meta()
        fibers = store.fibers()
        by_anchor = {fiber.anchor_id: fiber for fiber in fibers}
        aliases = store.aliases()
        nodes = []
        for neuron in store.neurons():
            fiber = by_anchor.get(neuron.id)
            nodes.append(
                {
                    "id": neuron.id,
                    "kind": neuron.kind,
                    "kind_label": "记忆" if fiber else NODE_KINDS.get(neuron.kind, neuron.kind),
                    "name": content(fiber) if fiber else neuron.name,
                    "aliases": aliases.get(neuron.id, []),
                    "innate": neuron.innate,
                    "memory_type": fiber.memory_type if fiber else None,
                    "is_user": neuron.id == meta["user_id"],
                    "is_self": neuron.id == meta["self_id"],
                }
            )
        links = [
            {
                "id": synapse.id,
                "source_id": synapse.source_id,
                "target_id": synapse.target_id,
                "type": synapse.type,
                "type_label": RELATIONS.get(synapse.type, (synapse.type,))[0],
                "label": synapse.label,
                "weight": round(link_weight(synapse, now), 3),
                "innate": synapse.innate,
                "grown": synapse.type == "co_recalled",
            }
            for synapse in store.synapses()
        ]
        memories = [
            {
                "id": fiber.id,
                "anchor_id": fiber.anchor_id,
                "type": MEMORY_TYPES.get(fiber.memory_type, fiber.memory_type),
                "statement": fiber.statement,
                "gist": fiber.gist,
                "detail": fiber.detail,
                "evidence": fiber.evidence,
                "source": SOURCES.get(fiber.source, fiber.source),
                "importance": fiber.importance,
                "emotion": None if fiber.emotion is None else fiber.emotion.model_dump(),
                "confidence": fiber.confidence,
                "strength": round(fiber.strength, 3),
                "stage": STAGES.get(fiber.stage, fiber.stage),
                "detail_level": fiber.detail_level,
                "state": STATES.get(fiber.state, fiber.state),
                "clarity": CLARITY.get(clarity(fiber), ""),
                "occurred_start": fiber.occurred_start,
                "due_at": fiber.due_at,
                "trigger": fiber.trigger,
                "created_at": fiber.created_at,
                "recall_count": fiber.recall_count,
                "cues": fiber.cues,
                "neuron_ids": fiber.neuron_ids,
                "synapse_ids": fiber.synapse_ids,
            }
            for fiber in fibers
        ]
        journal = [
            {
                "at": row["at"],
                "phase": row["phase"],
                "op": row["op"],
                "status": row["status"],
                "label": row["label"],
                "reason": row["reason"],
                "fiber_id": row["fiber_id"],
            }
            for row in store.journal(300)
        ]
        mood = store.mood()
        return {
            "nodes": nodes,
            "links": links,
            "memories": memories,
            "journal": journal,
            "mind": {
                "baseline_mood": meta["baseline_mood"],
                "mood": None if mood is None else mood.model_dump(),
                "counts": store.counts(),
                "identity_text": meta["identity_text"],
            },
        }
    finally:
        store.close()
