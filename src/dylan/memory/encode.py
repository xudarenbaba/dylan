"""Neuron reuse, dedup, inverse edges, provenance caps and identity seeding."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from dylan.clock import dump_time
from dylan.memory.anchors import query_dates
from dylan.memory.compress import summarize
from dylan.memory.constants import (
    DEDUP_BUMP,
    DEFAULT_PRIORITY,
    DEFAULT_SYNAPSE_WEIGHT,
    EVIDENCE_AGAINST_SCALE,
    EVIDENCE_FOR_STEP,
    HOT_TYPES,
    HYPOTHESIS_PRIOR,
    IDENTITY_PRIORITY,
    LEXICON_WEIGHT,
    PINNED_ON_CREATE,
    TRUST_CAP,
)
from dylan.memory.decay import expires_on
from dylan.memory.jaccard import jaccard
from dylan.memory.lexicon_zh import TIME_GROUPS
from dylan.memory.limits import Limits
from dylan.memory.model import Fiber, Provenance
from dylan.memory.roles import direction_for, inverse_type
from dylan.memory.stage import maybe_working, note_rehearsal
from dylan.memory.store import MemoryStore, day_key


@dataclass
class Draft:
    memory_type: str
    summary: str
    body: str
    neurons: list[tuple[str, str]] = field(default_factory=list)
    links: list[tuple[str, str, str]] = field(default_factory=list)
    source: str = "user_input"
    confidence: str = "high"
    trust: float = 0.9
    tags: list[str] = field(default_factory=list)
    supersede_previous: str | None = None
    contradicts_previous: bool = False
    auto_session: bool = False


def seed_lexicon(store: MemoryStore) -> None:
    for words in TIME_GROUPS.values():
        neurons = [store.ensure_neuron("time", word) for word in words]
        for index, left in enumerate(neurons):
            for right in neurons[index + 1 :]:
                store.add_synapse(
                    left.id,
                    right.id,
                    "similar_to",
                    direction=direction_for("similar_to"),
                    base_weight=LEXICON_WEIGHT,
                )


def seed_identity(store: MemoryStore, text: str) -> Fiber:
    neuron = store.ensure_neuron("concept", "dylan", pinned=True)
    return _insert_fiber(
        store,
        Draft(
            memory_type="identity",
            summary=text,
            body=text,
            neurons=[("concept", "dylan")],
            source="user_input",
            confidence="verified",
            trust=TRUST_CAP["user_input"],
        ),
        [neuron.id],
        [],
    )


def bootstrap(store: MemoryStore, identity_text: str) -> None:
    with store.transaction():
        seed_lexicon(store)
        if not store.identity_pinned():
            seed_identity(store, identity_text)


def reset_identity(store: MemoryStore, identity_text: str) -> None:
    with store.transaction():
        for fiber in list(store.fibers()):
            if fiber.memory_type == "identity":
                store.delete_fiber(fiber.id)
        seed_identity(store, identity_text)


def clamp_provenance(draft: Draft) -> Provenance | None:
    source = draft.source
    if source not in TRUST_CAP:
        return None
    confidence = draft.confidence
    if source == "dream":
        confidence = "inferred"
    if source == "ai_inference" and confidence in {"verified", "high"}:
        confidence = "medium"
    if confidence not in {"verified", "high", "medium", "low", "inferred"}:
        confidence = "medium"
    trust = min(float(draft.trust), TRUST_CAP[source])
    return Provenance(source=source, confidence=confidence, trust=trust)


def find_duplicate(store: MemoryStore, summary: str, limits: Limits | None = None) -> Fiber | None:
    limits = limits or Limits()
    best: Fiber | None = None
    best_score = 0.0
    for fiber in store.fibers():
        if fiber.state != "active" or fiber.memory_type == "identity":
            continue
        score = jaccard(fiber.summary, summary)
        if score >= limits.dedup_jaccard and score > best_score:
            best = fiber
            best_score = score
    return best


def insert_generated(
    store: MemoryStore,
    draft: Draft,
    neuron_ids: list[str],
    synapse_ids: list[str] | None = None,
) -> Fiber:
    return _insert_fiber(store, draft, neuron_ids, synapse_ids or [])


def write_draft(store: MemoryStore, draft: Draft, limits: Limits | None = None) -> Fiber | None:
    provenance = clamp_provenance(draft)
    if provenance is None or not draft.summary.strip():
        return None
    duplicate = find_duplicate(store, draft.summary, limits)
    if duplicate is not None and not duplicate.pinned:
        return _rehearse(store, duplicate)
    if duplicate is not None:
        return duplicate
    neuron_ids, synapse_ids = _materialize(store, draft)
    fiber = _insert_fiber(store, draft, neuron_ids, synapse_ids, provenance)
    _apply_supersede(store, fiber, draft)
    _apply_contradicts(store, fiber, draft)
    _apply_evidence_links(store, draft)
    return fiber


def write_drafts(
    store: MemoryStore, drafts: list[Draft], limits: Limits | None = None
) -> list[Fiber]:
    written: list[Fiber] = []
    for draft in drafts:
        fiber = write_draft(store, draft, limits)
        if fiber is not None:
            written.append(fiber)
    return written


def forget_fragment(store: MemoryStore, fragment: str) -> list[str]:
    fragment = fragment.strip()
    if len(fragment) < 1:
        return []
    messages: list[str] = []
    for fiber in list(store.fibers()):
        if fiber.state != "active":
            continue
        blob = " ".join([fiber.summary, fiber.body or "", " ".join(fiber.tags)])
        if fragment not in blob:
            continue
        from dylan.memory.lifecycle import soft_delete

        updated, reason = soft_delete(store, fiber)
        if updated is None and reason:
            messages.append(reason)
    return messages


def add_evidence(store: MemoryStore, hypothesis: Fiber, *, support: bool, text: str) -> Fiber:
    evidence = store.ensure_neuron("concept", text)
    synapse_type = "evidence_for" if support else "evidence_against"
    _link(store, evidence.id, hypothesis.anchor_neuron_id, synapse_type, DEFAULT_SYNAPSE_WEIGHT)
    current = (
        HYPOTHESIS_PRIOR if hypothesis.confidence_value is None else hypothesis.confidence_value
    )
    if support:
        current = current + EVIDENCE_FOR_STEP * (1.0 - current)
    else:
        current = current * EVIDENCE_AGAINST_SCALE
    updated = hypothesis.model_copy(update={"confidence_value": current})
    store.save_fiber(updated)
    return store.fiber(updated.id) or updated


def write_episode(
    store: MemoryStore,
    text: str,
    neuron_ids: list[str],
    *,
    auto_session: bool,
) -> Fiber | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    summary, essence, ghost = summarize(cleaned)
    if not neuron_ids:
        neuron = store.ensure_neuron("episode", summary[:40] or "会话")
        neuron_ids = [neuron.id]
    draft = Draft(
        memory_type="episode",
        summary=summary or cleaned[:300],
        body=cleaned,
        source="user_input",
        confidence="high",
        trust=TRUST_CAP["user_input"],
        auto_session=auto_session,
    )
    provenance = clamp_provenance(draft)
    fiber = _insert_fiber(store, draft, neuron_ids, [], provenance)
    fiber.essence = essence
    fiber.ghost = ghost
    store.save_fiber(fiber)
    return fiber


def _rehearse(store: MemoryStore, fiber: Fiber) -> Fiber:
    today = day_key(dump_time(store.clock.now()))
    updated = note_rehearsal(fiber, today)
    updated = updated.model_copy(
        update={
            "conductivity": min(1.0, updated.conductivity + DEDUP_BUMP),
            "base_conductivity": min(1.0, updated.base_conductivity + DEDUP_BUMP),
        }
    )
    updated = maybe_working(updated)
    store.save_fiber(updated)
    return updated


def _materialize(store: MemoryStore, draft: Draft) -> tuple[list[str], list[str]]:
    by_content: dict[str, str] = {}
    ordered: list[str] = []
    for kind, content in draft.neurons:
        content = content.strip()
        if not content:
            continue
        neuron = store.ensure_neuron(kind, content, pinned=draft.memory_type == "identity")
        if neuron.id not in ordered:
            ordered.append(neuron.id)
        by_content[content] = neuron.id
    if not ordered:
        neuron = store.ensure_neuron("concept", draft.summary[:80] or draft.summary)
        ordered.append(neuron.id)
        by_content[draft.summary] = neuron.id
    synapse_ids: list[str] = []
    for source, target, synapse_type in draft.links:
        source_id = by_content.get(source) or store.ensure_neuron("concept", source).id
        target_id = by_content.get(target) or store.ensure_neuron("concept", target).id
        if source_id not in ordered:
            ordered.append(source_id)
        if target_id not in ordered:
            ordered.append(target_id)
        synapse_ids.extend(_link(store, source_id, target_id, synapse_type, DEFAULT_SYNAPSE_WEIGHT))
    return ordered, synapse_ids


def _link(
    store: MemoryStore,
    source_id: str,
    target_id: str,
    synapse_type: str,
    weight: float,
) -> list[str]:
    if source_id == target_id:
        return []
    created = store.add_synapse(
        source_id,
        target_id,
        synapse_type,
        direction=direction_for(synapse_type),
        base_weight=weight,
    )
    ids = [created.id]
    inverse = inverse_type(synapse_type)
    if inverse is not None:
        back = store.add_synapse(
            target_id,
            source_id,
            inverse,
            direction=direction_for(inverse),
            base_weight=weight,
        )
        ids.append(back.id)
    return ids


def _insert_fiber(
    store: MemoryStore,
    draft: Draft,
    neuron_ids: list[str],
    synapse_ids: list[str],
    provenance: Provenance | None = None,
) -> Fiber:
    provenance = provenance or clamp_provenance(draft)
    assert provenance is not None
    now = store.clock.now()
    stamp = dump_time(now)
    summary, essence, ghost = summarize(draft.summary)
    pinned = draft.memory_type in PINNED_ON_CREATE
    tier = "hot" if draft.memory_type in HOT_TYPES or pinned else "warm"
    priority = IDENTITY_PRIORITY if draft.memory_type in PINNED_ON_CREATE else DEFAULT_PRIORITY
    expiry = expires_on(draft.memory_type, now)
    start, end = _time_span(draft.body or draft.summary)
    confidence_value = HYPOTHESIS_PRIOR if draft.memory_type == "hypothesis" else None
    fiber = Fiber(
        id=str(uuid4()),
        anchor_neuron_id=neuron_ids[0],
        neuron_ids=neuron_ids,
        synapse_ids=synapse_ids,
        conductivity=1.0,
        base_conductivity=1.0,
        summary=summary or draft.summary,
        essence=essence,
        ghost=ghost,
        body=draft.body or draft.summary,
        compression_tier=0,
        stage="episodic",
        memory_type=draft.memory_type,
        priority=priority,
        tier=tier,
        state="active",
        pinned=pinned,
        time_start=start,
        time_end=end,
        expires_at=None if expiry is None else dump_time(expiry),
        rehearsal_count=0,
        last_conducted_at=stamp,
        last_activated_at=stamp,
        created_at=stamp,
        decay_cursor=stamp,
        provenance=provenance,
        recall_dates=[day_key(stamp)],
        confidence_value=confidence_value,
        tags=_clean_tags(draft.tags),
        auto_session=draft.auto_session,
        frequency=1,
    )
    store.insert_fiber(fiber)
    return fiber


def _time_span(text: str) -> tuple[str | None, str | None]:
    dates = query_dates(text)
    if not dates:
        return None, None
    start = dates[0]
    end = dates[-1] + timedelta(days=1)
    return dump_time(start), dump_time(end)


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        value = tag.strip()
        if not value:
            continue
        chars = []
        for char in value:
            if ("A" <= char <= "Z") or ("a" <= char <= "z"):
                chars.append(char.casefold())
            else:
                chars.append(char)
        normalized = "".join(chars)
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _apply_supersede(store: MemoryStore, fiber: Fiber, draft: Draft) -> None:
    if draft.supersede_previous != "evolves_from":
        return
    previous = [
        item
        for item in store.fibers()
        if item.id != fiber.id
        and item.memory_type == fiber.memory_type
        and item.state == "active"
    ]
    if not previous:
        return
    older = previous[-1]
    _link(
        store,
        fiber.anchor_neuron_id,
        older.anchor_neuron_id,
        "evolves_from",
        DEFAULT_SYNAPSE_WEIGHT,
    )


def _apply_contradicts(store: MemoryStore, fiber: Fiber, draft: Draft) -> None:
    if not draft.contradicts_previous:
        return
    previous = [
        item
        for item in store.fibers()
        if item.id != fiber.id
        and item.state == "active"
        and not item.pinned
        and item.memory_type != "identity"
    ]
    if not previous:
        return
    older = previous[-1]
    _link(
        store,
        fiber.anchor_neuron_id,
        older.anchor_neuron_id,
        "contradicts",
        DEFAULT_SYNAPSE_WEIGHT,
    )


def _apply_evidence_links(store: MemoryStore, draft: Draft) -> None:
    for source, target, synapse_type in draft.links:
        if synapse_type not in {"evidence_for", "evidence_against"}:
            continue
        for fiber in store.fibers():
            if fiber.memory_type != "hypothesis" or fiber.state != "active":
                continue
            anchor = store.neuron(fiber.anchor_neuron_id)
            if anchor is None or anchor.content != target:
                continue
            support = synapse_type == "evidence_for"
            add_evidence(store, fiber, support=support, text=source)
