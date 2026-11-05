"""Birth, sleep and replacing the innate self. The model proposes; the writer decides."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta, tzinfo

from dylan.clock import dump_time, load_time
from dylan.memory.constants import (
    DEFAULT_BASELINE_MOOD,
    HER_TURN,
    LABEL_CHARS,
    MAX_NAME_CHARS,
    MAX_SLEEP_CANDIDATES,
    PENDING_MAX_ATTEMPTS,
    RECALLABLE_STATES,
)
from dylan.memory.maintain import maintain
from dylan.memory.model import Fiber, Mood, Session, Turn
from dylan.memory.ops import Context, Outcome, Writer
from dylan.memory.store import MemoryStore
from dylan.memory.text import clip, key_of, mask_secrets


def identity_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def letter_changed(store: MemoryStore, text: str) -> bool:
    stored = store.meta()["identity_hash"]
    return bool(stored) and stored != identity_hash(text)


@dataclass
class Handles:
    """Short names the model may use to point at memories it was shown."""

    by_handle: dict[str, str] = field(default_factory=dict)

    def add(self, fiber: Fiber) -> str:
        for handle, fiber_id in self.by_handle.items():
            if fiber_id == fiber.id:
                return handle
        handle = f"m{len(self.by_handle) + 1}"
        self.by_handle[handle] = fiber.id
        return handle


def birth(
    store: MemoryStore, letter: str, proposal: dict, tz: tzinfo, api_key: str = ""
) -> Outcome:
    """Write the innate self from her own reading of the letter."""
    me_name = clip(proposal.get("self_name"), MAX_NAME_CHARS) or "dylan"
    user_name = clip(proposal.get("user_name"), MAX_NAME_CHARS)
    if not user_name:
        raise ValueError("身份信里没有读出写信的人")
    baseline = clip(proposal.get("baseline_mood"), LABEL_CHARS) or DEFAULT_BASELINE_MOOD
    with store.transaction():
        me = store.ensure_neuron("person", me_name, innate=True)
        user = store.ensure_neuron("person", user_name, innate=True)
        for alias in proposal.get("user_aliases") or []:
            if isinstance(alias, str) and key_of(alias) != key_of(user_name):
                store.add_alias(user.id, alias.strip()[:MAX_NAME_CHARS])
        store.set_meta(
            user_id=user.id,
            self_id=me.id,
            identity_text=letter.strip(),
            identity_hash=identity_hash(letter),
            baseline_mood=baseline,
        )
        ctx = Context(phase="birth", tz=tz, api_key=api_key, letter=letter)
        outcome = Writer(store, ctx).apply(proposal.get("ops"))
        if not outcome.created:
            raise ValueError("没有从身份信里形成任何天生记忆")
    return outcome


def reset_innate(
    store: MemoryStore, letter: str, proposal: dict, tz: tzinfo, api_key: str = ""
) -> Outcome:
    """Replace only what she was born with. Her life since then stays."""
    with store.transaction():
        for fiber in store.fibers():
            if fiber.memory_type == "innate":
                store.delete_fiber(fiber.id)
        for synapse in store.synapses():
            if synapse.innate:
                store.delete_synapse(synapse.id)
        store.conn.execute("UPDATE neurons SET innate = 0")
        meta = store.meta()
        me_name = clip(proposal.get("self_name"), MAX_NAME_CHARS) or "dylan"
        user_name = clip(proposal.get("user_name"), MAX_NAME_CHARS)
        if not user_name:
            raise ValueError("身份信里没有读出写信的人")
        store.rename_neuron(meta["self_id"], me_name)
        store.rename_neuron(meta["user_id"], user_name)
        store.mark_innate(meta["self_id"])
        store.mark_innate(meta["user_id"])
        store.set_meta(
            identity_text=letter.strip(),
            identity_hash=identity_hash(letter),
            baseline_mood=clip(proposal.get("baseline_mood"), LABEL_CHARS) or DEFAULT_BASELINE_MOOD,
        )
        ctx = Context(phase="birth", tz=tz, api_key=api_key, letter=letter)
        outcome = Writer(store, ctx).apply(proposal.get("ops"))
        if not outcome.created:
            raise ValueError("没有从身份信里形成任何天生记忆")
    return outcome


def sessions_to_sleep(store: MemoryStore) -> list[Session]:
    return [session for session in store.sessions() if not session.slept]


def sleep_material(
    store: MemoryStore, session: Session, handles: Handles
) -> tuple[list[tuple[str, Fiber]], str]:
    """What she reviews in sleep: what changed during that conversation and what it touched."""
    since = session.started_at
    touched = store.touched_since(since)
    chosen: list[Fiber] = []
    for fiber_id in touched:
        fiber = store.fiber(fiber_id)
        if fiber is None or fiber.memory_type == "innate" or fiber.state not in RECALLABLE_STATES:
            continue
        chosen.append(fiber)
    near = _neighbours(store, chosen)
    for fiber in near:
        if fiber not in chosen:
            chosen.append(fiber)
    listed = [(handles.add(fiber), fiber) for fiber in chosen[:MAX_SLEEP_CANDIDATES]]
    turns = store.turns(session.id)
    transcript = "\n".join(_transcript_line(turn) for turn in turns)
    return listed, transcript


def finish_sleep(
    store: MemoryStore,
    session: Session,
    proposal: dict | None,
    handles: Handles,
    tz: tzinfo,
    api_key: str = "",
) -> Outcome:
    turns = store.turns(session.id)
    start = turns[0].at if turns else session.started_at
    end = turns[-1].at if turns else (session.ended_at or session.started_at)
    end = dump_time(load_time(end) + timedelta(minutes=1))
    with store.transaction():
        outcome = Outcome()
        if proposal is not None:
            ctx = Context(
                phase="sleep",
                tz=tz,
                api_key=api_key,
                handles=dict(handles.by_handle),
                session_id=session.id,
                session_span=(start, end),
            )
            outcome = Writer(store, ctx).apply(proposal.get("ops"))
            mood = proposal.get("mood")
            if isinstance(mood, dict) and mood.get("label"):
                store.set_mood(_mood(mood, store, api_key))
            summary = mask_secrets(clip(proposal.get("summary"), 300), api_key)[0]
            if summary:
                store.set_session_summary(session.id, summary)
        store.end_session(session.id, end)
        store.mark_slept(session.id)
        if proposal is not None:
            store.forget_turns(session.id)
    maintain(store)
    return outcome


def discard_empty(store: MemoryStore, session: Session) -> bool:
    if store.turns(session.id):
        return False
    with store.transaction():
        store.delete_session(session.id)
    return True


def give_up(store: MemoryStore, session_id: str) -> bool:
    """Count one failed sleep. After a few, keep what was noted and let the rest go."""
    with store.transaction():
        attempts = store.bump_sleep_attempts(session_id)
    return attempts >= PENDING_MAX_ATTEMPTS


def _mood(raw: dict, store: MemoryStore, api_key: str) -> Mood:
    from dylan.memory.ops import _float

    return Mood(
        label=mask_secrets(clip(raw.get("label"), LABEL_CHARS), api_key)[0],
        intensity=_float(raw.get("intensity"), 0.5, 0.0, 1.0),
        cause=mask_secrets(clip(raw.get("cause"), 40), api_key)[0],
        at=store.now(),
    )


def _neighbours(store: MemoryStore, fibers: list[Fiber]) -> list[Fiber]:
    """Older memories that share a person, place or thing with what just happened."""
    if not fibers:
        return []
    anchors = {fiber.anchor_id for fiber in fibers}
    members: set[str] = set()
    for fiber in fibers:
        members.update(node for node in fiber.neuron_ids if node not in anchors)
    meta = store.meta()
    members.discard(meta["self_id"])
    found: list[Fiber] = []
    for fiber in store.fibers({"active", "superseded", "done"}):
        if fiber.memory_type == "innate" or fiber.anchor_id in anchors:
            continue
        shared = members.intersection(fiber.neuron_ids)
        if shared - {meta["user_id"]}:
            found.append(fiber)
    found.sort(key=lambda fiber: fiber.importance * fiber.strength, reverse=True)
    return found


def _transcript_line(turn: Turn) -> str:
    stamp = _clock(turn.at)
    if turn.user_text == HER_TURN:
        return f"{stamp} 她：{turn.reply_text}"
    return f"{stamp} 他：{turn.user_text}\n{stamp} 她：{turn.reply_text}"


def _clock(stamp: str) -> str:
    return stamp[11:16]
