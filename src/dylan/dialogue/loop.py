"""One brain, one conversation. She hears, remembers, replies, notes the moment, and sleeps."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import tzinfo

from dylan.clock import Clock, zone
from dylan.config import Settings
from dylan.dialogue.prompt import (
    birth_messages,
    candidate_lines,
    note_messages,
    reply_messages,
    sleep_messages,
)
from dylan.errors import BirthFailed, DylanError
from dylan.memory.awareness import build_awareness
from dylan.memory.constants import (
    MAX_CANDIDATES,
    PRIVACY_NOTICE,
    SESSION_CANDIDATES,
    USED_BUMP,
)
from dylan.memory.life import (
    Handles,
    birth,
    discard_empty,
    finish_sleep,
    give_up,
    reset_innate,
    sessions_to_sleep,
    sleep_material,
)
from dylan.memory.maintain import maintain
from dylan.memory.model import Fiber, Mood
from dylan.memory.ops import Context, Outcome, Writer, _float
from dylan.memory.physiology import clarity
from dylan.memory.recall import Recall, persist_recall, recall
from dylan.memory.render import describe, fit
from dylan.memory.store import MemoryStore
from dylan.memory.text import clip, mask_secrets

MASKED_NOTICE = "这句话里像密钥的部分没有记住"
NOTE_FAILED = "上一轮没有记下来，睡觉时会再整理"
SLEEP_FAILED = "这次的睡眠整理没有完成，下次启动时会再整理"
SLEEP_GAVE_UP = "睡眠整理多次失败，这次会话只保留了已经记下的部分"


def in_background(call: Callable[[], object]) -> Future:
    """One model request off the main thread. Daemon, so Ctrl-C never waits for it."""
    future: Future = Future()

    def run() -> None:
        try:
            future.set_result(call())
        except BaseException as exc:
            future.set_exception(exc)

    threading.Thread(target=run, daemon=True).start()
    return future


def _masked(text: object, limit: int, api_key: str) -> str:
    return mask_secrets(clip(text, limit), api_key)[0]


def be_born(store: MemoryStore, letter: str, model: object, settings: Settings) -> Outcome:
    tz = zone(settings.dylan_timezone)
    try:
        proposal = model.complete_json(birth_messages(letter))  # type: ignore[attr-defined]
        return birth(store, letter, proposal, tz, settings.deepseek_api_key)
    except DylanError as exc:
        raise BirthFailed(exc.category) from exc
    except Exception as exc:
        raise BirthFailed(str(exc) or "身份信没有读懂") from exc


def be_reborn(store: MemoryStore, letter: str, model: object, settings: Settings) -> Outcome:
    tz = zone(settings.dylan_timezone)
    try:
        proposal = model.complete_json(birth_messages(letter))  # type: ignore[attr-defined]
        return reset_innate(store, letter, proposal, tz, settings.deepseek_api_key)
    except DylanError as exc:
        raise BirthFailed(exc.category) from exc
    except Exception as exc:
        raise BirthFailed(str(exc) or "身份信没有读懂") from exc


def sleep_pending(store: MemoryStore, model: object, settings: Settings, stderr: object) -> int:
    """Finish every conversation that has not been slept on yet. Returns how many."""
    tz = zone(settings.dylan_timezone)
    done = 0
    for session in sessions_to_sleep(store):
        if discard_empty(store, session):
            continue
        _catch_up_notes(store, session.id, model, settings, stderr)
        handles = Handles()
        listed, transcript = sleep_material(store, session, handles)
        now = store.clock.now()
        clarity_of = {fiber.id: clarity(fiber) for _handle, fiber in listed}
        candidates = candidate_lines(listed, clarity_of, tz, now)
        messages = sleep_messages(
            who=_names(store),
            now=now,
            tz=tz,
            transcript=transcript,
            summary=session.summary,
            candidates=candidates,
        )
        try:
            proposal = model.complete_json(messages)  # type: ignore[attr-defined]
            if not isinstance(proposal, dict):
                raise ValueError("sleep")
        except Exception:
            if not give_up(store, session.id):
                stderr.write(SLEEP_FAILED + "\n")  # type: ignore[attr-defined]
                continue
            stderr.write(SLEEP_GAVE_UP + "\n")  # type: ignore[attr-defined]
            proposal = None
        outcome = finish_sleep(store, session, proposal, handles, tz, settings.deepseek_api_key)
        _show(outcome, settings, stderr, "睡眠")
        done += 1
    if not done:
        maintain(store)
    return done


@dataclass
class Pending:
    future: Future
    turn_id: str
    user_text: str
    reply_text: str
    handles: dict[str, str]
    summary_before: str
    recent: list[tuple[str, str]] = field(default_factory=list)


class Conversation:
    def __init__(
        self,
        store: MemoryStore,
        settings: Settings,
        model: object,
        clock: Clock,
    ) -> None:
        self.store = store
        self.settings = settings
        self.model = model
        self.clock = clock
        self.tz: tzinfo = zone(settings.dylan_timezone)
        self.letter = store.meta()["identity_text"]
        self.session = None
        self.turns: list[tuple[str, str]] = []
        self.summary = ""
        self.carry: list[str] = []
        self.pending: Pending | None = None
        self.warning = ""

    def turn(self, text: str, stdout: object, stderr: object) -> None:
        self._settle_note(stderr)
        if self.warning:
            stderr.write(self.warning + "\n")  # type: ignore[attr-defined]
            self.warning = ""
        if self.session is None:
            with self.store.transaction():
                self.session = self.store.start_session()
        masked, hidden = mask_secrets(text, self.settings.deepseek_api_key)
        if hidden:
            stderr.write(MASKED_NOTICE + "\n")  # type: ignore[attr-defined]
        awareness = build_awareness(
            self.store,
            self.tz,
            current_session=self.session.id,
            budget=self.settings.dylan_awareness_chars,
        )
        context = [masked, *[said for said, _ in reversed(self.turns[-2:])]]
        found = recall(
            self.store,
            context,
            self.tz,
            carry=self.carry,
            exclude=set(awareness.fiber_ids),
            limit=self.settings.dylan_recall_limit,
        )
        now = self.clock.now()
        lines = [describe(hit.fiber, hit.clarity, self.tz, now) for hit in found.hits]
        recalled = "\n".join(fit(lines, self.settings.dylan_recall_chars))
        if self.settings.dylan_show_mind:
            stderr.write(f"〔常驻〕\n{awareness.text}\n〔想起〕\n{recalled or '无'}\n")  # type: ignore[attr-defined]
        messages = reply_messages(
            letter=self.letter,
            awareness=awareness.text,
            recalled=recalled,
            turns=self.turns[-self.settings.dylan_buffer_turns :],
            user_text=masked,
        )
        chunks: list[str] = []
        try:
            for chunk in self.model.stream_reply(messages):  # type: ignore[attr-defined]
                chunks.append(chunk)
                stdout.write(chunk)  # type: ignore[attr-defined]
                stdout.flush()  # type: ignore[attr-defined]
        except DylanError as exc:
            stderr.write(exc.category + "\n")  # type: ignore[attr-defined]
            if chunks and not str(chunks[-1]).endswith("\n"):
                stdout.write("\n")  # type: ignore[attr-defined]
            return
        reply = "".join(chunks)
        if not reply.endswith("\n"):
            stdout.write("\n")  # type: ignore[attr-defined]
        reply_masked, _ = mask_secrets(reply, self.settings.deepseek_api_key)
        with self.store.transaction():
            persist_recall(self.store, found, self.tz)
            turn = self.store.add_turn(self.session.id, masked, reply_masked)
        self._start_note(turn.id, masked, reply_masked, found, awareness.fiber_ids)
        self.turns.append((masked, reply_masked))
        self.carry = [hit.fiber.id for hit in found.hits][:3]

    def finish(self, stderr: object) -> None:
        self._settle_note(stderr)
        if self.session is None:
            return
        sleep_pending(self.store, self.model, self.settings, stderr)

    def abandon(self) -> None:
        self.pending = None

    # noting the moment

    def _start_note(
        self,
        turn_id: str,
        user_text: str,
        reply_text: str,
        found: Recall,
        aware_ids: list[str],
    ) -> None:
        handles = Handles()
        listed: list[tuple[str, Fiber]] = []
        clarity_of: dict[str, str] = {}
        for hit in found.hits:
            listed.append((handles.add(hit.fiber), hit.fiber))
            clarity_of[hit.fiber.id] = hit.clarity
        for fiber_id in [*aware_ids, *self._session_fibers()]:
            fiber = self.store.fiber(fiber_id)
            if fiber is None or fiber.id in clarity_of or len(listed) >= MAX_CANDIDATES:
                continue
            listed.append((handles.add(fiber), fiber))
            clarity_of[fiber.id] = clarity(fiber)
        now = self.clock.now()
        recent = list(self.turns[-2:])
        messages = note_messages(
            who=_names(self.store),
            now=now,
            tz=self.tz,
            recent=recent,
            user_text=user_text,
            reply_text=reply_text,
            candidates=candidate_lines(listed, clarity_of, self.tz, now),
            summary=self.summary,
        )
        future = in_background(lambda: self.model.complete_json(messages))  # type: ignore[attr-defined]
        self.pending = Pending(
            future=future,
            turn_id=turn_id,
            user_text=user_text,
            reply_text=reply_text,
            handles=dict(handles.by_handle),
            summary_before=self.summary,
            recent=recent,
        )

    def _settle_note(self, stderr: object) -> None:
        pending = self.pending
        if pending is None:
            return
        self.pending = None
        try:
            proposal = pending.future.result()
            if not isinstance(proposal, dict):
                raise ValueError("note")
        except Exception:
            with self.store.transaction():
                self.store.bump_attempts(pending.turn_id)
            self.warning = NOTE_FAILED
            return
        try:
            session_id = self.session.id
            outcome = apply_note(self.store, self.settings, self.tz, pending, proposal, session_id)
        except Exception:
            self.warning = NOTE_FAILED
            return
        summary = _masked(proposal.get("summary"), 300, self.settings.deepseek_api_key)
        if summary:
            self.summary = summary
        _show(outcome, self.settings, stderr, "记下")

    def _session_fibers(self) -> list[str]:
        if self.session is None:
            return []
        ids = self.store.touched_since(self.session.started_at)
        return ids[:SESSION_CANDIDATES]


def apply_note(
    store: MemoryStore,
    settings: Settings,
    tz: tzinfo,
    pending: Pending,
    proposal: dict,
    session_id: str,
) -> Outcome:
    ctx = Context(
        phase="note",
        tz=tz,
        api_key=settings.deepseek_api_key,
        user_text=pending.user_text,
        reply_text=pending.reply_text,
        handles=pending.handles,
        session_id=session_id,
    )
    api_key = settings.deepseek_api_key
    with store.transaction():
        writer = Writer(store, ctx)
        outcome = writer.apply(proposal.get("ops"))
        writer.strengthen_handles(proposal.get("used"), USED_BUMP, count=True)
        mood = proposal.get("mood")
        if isinstance(mood, dict) and _masked(mood.get("label"), 10, api_key):
            store.set_mood(
                Mood(
                    label=_masked(mood.get("label"), 10, api_key),
                    intensity=_float(mood.get("intensity"), 0.5, 0.0, 1.0),
                    cause=_masked(mood.get("cause"), 40, api_key),
                    at=store.now(),
                )
            )
        summary = _masked(proposal.get("summary"), 300, api_key)
        if summary:
            store.set_session_summary(session_id, summary)
        store.mark_noted(pending.turn_id)
    return outcome


def _catch_up_notes(
    store: MemoryStore, session_id: str, model: object, settings: Settings, stderr: object
) -> None:
    """Turns that were never noted get one more try before sleep reviews them."""
    tz = zone(settings.dylan_timezone)
    turns = [turn for turn in store.pending_turns() if turn.session_id == session_id]
    session = store.session(session_id)
    summary = session.summary if session else ""
    for turn in turns:
        now = store.clock.now()
        messages = note_messages(
            who=_names(store),
            now=now,
            tz=tz,
            recent=[],
            user_text=turn.user_text,
            reply_text=turn.reply_text,
            candidates="（没有）",
            summary=summary,
        )
        pending = Pending(
            future=Future(),
            turn_id=turn.id,
            user_text=turn.user_text,
            reply_text=turn.reply_text,
            handles={},
            summary_before=summary,
        )
        try:
            proposal = model.complete_json(messages)  # type: ignore[attr-defined]
            if not isinstance(proposal, dict):
                raise ValueError("note")
            outcome = apply_note(store, settings, tz, pending, proposal, session_id)
            _show(outcome, settings, stderr, "补记")
        except Exception:
            with store.transaction():
                store.bump_attempts(turn.id)


def _names(store: MemoryStore) -> tuple[str, str]:
    meta = store.meta()
    user = store.neuron(meta["user_id"])
    me = store.neuron(meta["self_id"])
    return (user.name if user else "他", me.name if me else "dylan")


def _show(outcome: Outcome, settings: Settings, stderr: object, title: str) -> None:
    if not settings.dylan_show_mind or not outcome.lines:
        return
    stderr.write(f"〔{title}〕\n" + "\n".join(outcome.lines) + "\n")  # type: ignore[attr-defined]


def run_chat(conversation: Conversation, stdin: object, stdout: object, stderr: object) -> None:
    store = conversation.store
    if not store.privacy_shown():
        stdout.write(PRIVACY_NOTICE + "\n")  # type: ignore[attr-defined]
        stdout.flush()  # type: ignore[attr-defined]
        store.mark_privacy_shown()
    try:
        while True:
            line = stdin.readline()  # type: ignore[attr-defined]
            if line == "":
                break
            stripped = line.strip()
            if stripped == "":
                continue
            if stripped in {"exit", "quit"}:
                break
            conversation.turn(stripped, stdout, stderr)
    except BaseException:
        conversation.abandon()
        raise
    conversation.finish(stderr)
