"""Her proposals, checked by the brain's rules and written inside the caller's transaction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from dylan.clock import dump_time, load_time, local_day, parse_local
from dylan.memory.constants import (
    ANCHOR_KIND,
    CHANGEABLE_STATES,
    DEFAULT_IMPORTANCE,
    DEFAULT_LINK_WEIGHT,
    DETAIL_CHARS,
    EVIDENCE_AGAINST_SCALE,
    EVIDENCE_FOR_STEP,
    GIST_CHARS,
    INFERRED_CONFIDENCE,
    INFERRED_CONFIDENCE_CAP,
    INFERRED_SOURCES,
    LABEL_CHARS,
    MAX_ALIASES,
    MAX_BIRTH_OPS,
    MAX_CUES,
    MAX_LINKS,
    MAX_NAME_CHARS,
    MAX_NODES,
    MAX_NOTE_OPS,
    MAX_RELATIONS,
    MAX_SLEEP_OPS,
    MAX_SUPPRESS,
    MAX_TERM_CHARS,
    MEMORY_LINKS,
    MEMORY_TYPES,
    NODE_KINDS,
    NODE_RELATIONS,
    PRONOUNS_BOTH,
    PRONOUNS_SELF,
    PRONOUNS_USER,
    REINFORCE_BUMP,
    RELATION_ALIASES,
    RELIABLE_SOURCES,
    SLEEP_ONLY_TYPES,
    STATEMENT_CHARS,
    STOP_TERMS,
    TRIGGER_CHARS,
    UPDATE_BUMP,
)
from dylan.memory.model import Emotion, Fiber
from dylan.memory.physiology import hebbian, initial_strength, lowest_level, strengthen
from dylan.memory.store import MemoryStore, new_id
from dylan.memory.text import clip, contains_quote, has_secret, key_of, mask_secrets

PHASE_OPS = {
    "birth": frozenset({"add"}),
    "note": frozenset(
        {"add", "reinforce", "update", "supersede", "contradict", "complete", "suppress", "link"}
    ),
    "sleep": frozenset({"add", "update", "supersede", "contradict", "complete", "link", "merge"}),
}
PHASE_LIMIT = {"birth": MAX_BIRTH_OPS, "note": MAX_NOTE_OPS, "sleep": MAX_SLEEP_OPS}
OP_LABEL = {
    "add": "记下",
    "reinforce": "加强",
    "update": "更新",
    "supersede": "取代",
    "contradict": "标出矛盾",
    "complete": "完成",
    "suppress": "淡忘",
    "link": "关联",
    "merge": "合并",
}
_PLACE_TYPES = frozenset({"event", "session", "plan", "status"})
_GONE = frozenset({"suppressed", "merged"})
_STAGE_RANK = {"fresh": 0, "familiar": 1, "settled": 2}


class Rejected(Exception):
    pass


@dataclass
class Context:
    phase: str
    tz: tzinfo
    api_key: str = ""
    user_text: str = ""
    reply_text: str = ""
    letter: str = ""
    handles: dict[str, str] = field(default_factory=dict)
    session_id: str | None = None
    session_span: tuple[str, str] | None = None


@dataclass
class Outcome:
    created: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    rejected: int = 0


@dataclass
class Draft:
    memory_type: str
    about: str
    source: str
    statement: str
    detail: str = ""
    gist: str = ""
    evidence: str = ""
    importance: int = DEFAULT_IMPORTANCE
    emotion: Emotion | None = None
    confidence: float | None = None
    occurred: tuple[str | None, str | None] = (None, None)
    due_at: str | None = None
    trigger: str = ""
    valid_until: str | None = None
    parts: Parts | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class Parts:
    nodes: list[tuple[str, str, list[str]]] = field(default_factory=list)
    relations: list[tuple[str, str, str, str]] = field(default_factory=list)
    cues: list[str] = field(default_factory=list)
    links: list[tuple[str, str, bool]] = field(default_factory=list)


class Writer:
    def __init__(self, store: MemoryStore, ctx: Context) -> None:
        self.store = store
        self.ctx = ctx
        self.now: datetime = store.clock.now()
        self.stamp = dump_time(self.now)
        meta = store.meta()
        self.user_id: str = meta["user_id"]
        self.self_id: str = meta["self_id"]
        self.outcome = Outcome()
        self.suppressed = 0

    # entry points

    def apply(self, ops: object) -> Outcome:
        items = ops if isinstance(ops, list) else []
        allowed = PHASE_OPS[self.ctx.phase]
        for index, raw in enumerate(items):
            name = str(raw.get("op") or "").strip().lower() if isinstance(raw, dict) else ""
            try:
                if name not in allowed:
                    raise Rejected("这个时候不能这样记")
                if index >= PHASE_LIMIT[self.ctx.phase]:
                    raise Rejected("超出这一次的上限")
                if has_secret(json.dumps(raw, ensure_ascii=False), self.ctx.api_key):
                    raise Rejected("含有密钥形态的内容")
                getattr(self, f"_op_{name}")(raw)
            except Rejected as exc:
                self._reject(name or "未知", _label(raw), str(exc))
        if self.suppressed:
            self._trace_suppression()
        return self.outcome

    def strengthen_handles(self, values: object, bump: float, *, count: bool) -> None:
        seen: set[str] = set()
        for value in values if isinstance(values, list) else []:
            fiber = self._handle(value)
            if fiber is None or fiber.id in seen or fiber.state in _GONE:
                continue
            seen.add(fiber.id)
            self.store.save_fiber(strengthen(fiber, self.now, bump, self.ctx.tz, count=count))

    # ops

    def _op_add(self, raw: dict) -> None:
        draft = self._draft(raw)
        fiber = self._create(draft)
        self._accept("add", fiber.id, draft.statement, draft.notes)

    def _op_reinforce(self, raw: dict) -> None:
        target = self._target(raw)
        self.store.save_fiber(strengthen(target, self.now, REINFORCE_BUMP, self.ctx.tz, count=True))
        self.outcome.changed.append(target.id)
        self._accept("reinforce", target.id, _shown(target), [])

    def _op_update(self, raw: dict) -> None:
        target = self._target(raw)
        notes: list[str] = []
        statement = clip(raw.get("statement"), STATEMENT_CHARS)
        evidence = clip(raw.get("evidence"), DETAIL_CHARS)
        detail = clip(raw.get("detail"), DETAIL_CHARS)
        gist = clip(raw.get("gist"), GIST_CHARS)
        update: dict[str, object] = {}
        if statement:
            update.update(
                statement=statement,
                gist=gist or statement[:GIST_CHARS],
                detail=detail or evidence,
                evidence=evidence,
            )
        else:
            if gist:
                update["gist"] = gist
            if detail:
                update["detail"] = detail
        if evidence or raw.get("source"):
            claimed = str(raw.get("source") or target.source)
            about = self._about_name(target)
            source = self._source(target.memory_type, claimed, evidence, about, notes)
            if source in RELIABLE_SOURCES and target.source not in RELIABLE_SOURCES:
                update.update(source=source, confidence=None)
        if "importance" in raw:
            update["importance"] = _int(raw.get("importance"), target.importance, 1, 10)
        emotion = self._emotion(raw.get("emotion"))
        if emotion is not None:
            update["emotion"] = emotion
        if raw.get("occurred"):
            start, end = self._span(raw.get("occurred"))
            if start:
                update.update(occurred_start=start, occurred_end=end)
        for key, column in (("due", "due_at"), ("valid_until", "valid_until")):
            if raw.get(key):
                moment = self._moment(raw.get(key))
                if moment:
                    update[column] = moment
        if raw.get("trigger"):
            update["trigger"] = clip(raw.get("trigger"), TRIGGER_CHARS)
        if "confidence" in raw and target.source in INFERRED_SOURCES and "source" not in update:
            update["confidence"] = _float(
                raw.get("confidence"), INFERRED_CONFIDENCE, 0.05, INFERRED_CONFIDENCE_CAP
            )
        parts = self._parts(raw, notes)
        texts = [str(value) for value in update.values() if isinstance(value, str)]
        self._guard([*texts, *_part_texts(parts), emotion.label if emotion else ""])
        if not update and not _has_parts(parts):
            raise Rejected("没有要更新的内容")
        fresh = target.model_copy(update={**update, "updated_at": self.stamp})
        fresh = fresh.model_copy(update={"detail_level": lowest_level(fresh)})
        fresh = strengthen(fresh, self.now, UPDATE_BUMP, self.ctx.tz, count=True)
        self.store.save_fiber(fresh)
        self._attach(fresh, parts, fresh.memory_type)
        self.outcome.changed.append(fresh.id)
        self._accept("update", fresh.id, _shown(fresh), notes)

    def _op_supersede(self, raw: dict) -> None:
        target = self._target(raw, states=frozenset({"active"}))
        draft = self._draft(raw.get("with"), base=target)
        fiber = self._create(draft)
        valid = self.stamp
        if target.valid_until and target.valid_until < self.stamp:
            valid = target.valid_until
        self._set_state(target, "superseded", valid_until=valid)
        self._join(fiber, fiber.anchor_id, target.anchor_id, "supersedes")
        self._accept("supersede", fiber.id, f"{draft.statement} ← {_shown(target)}", draft.notes)

    def _op_contradict(self, raw: dict) -> None:
        target = self._target(raw, states=frozenset({"active"}))
        draft = self._draft(raw.get("with"), base=target)
        fiber = self._create(draft)
        self._join(fiber, fiber.anchor_id, target.anchor_id, "contradicts")
        self.outcome.changed.append(target.id)
        self._accept("contradict", fiber.id, f"{draft.statement} ↔ {_shown(target)}", draft.notes)

    def _op_complete(self, raw: dict) -> None:
        target = self._target(raw, states=frozenset({"active"}))
        if target.memory_type != "plan":
            raise Rejected("只有打算才能完成")
        draft = None
        if isinstance(raw.get("with"), dict):
            draft = self._draft(raw.get("with"), base=target, default_type="event")
        self._set_state(target, "done")
        label = _shown(target)
        notes: list[str] = []
        if draft is not None:
            fiber = self._create(draft)
            self._join(fiber, fiber.anchor_id, target.anchor_id, "completes")
            label = f"{draft.statement} → {label}"
            notes = draft.notes
        self._accept("complete", target.id, label, notes)

    def _op_suppress(self, raw: dict) -> None:
        if self.suppressed >= MAX_SUPPRESS:
            raise Rejected("一次淡忘不了这么多")
        target = self._target(raw)
        self._set_state(target, "suppressed")
        self.suppressed += 1
        self._accept("suppress", target.id, _shown(target), [])

    def _op_link(self, raw: dict) -> None:
        kind, swap = _canonical(raw.get("type"))
        if kind not in MEMORY_LINKS:
            raise Rejected("不认识的联系")
        left = self._handle(raw.get("source"))
        right = self._handle(raw.get("target"))
        if left is None or right is None or left.id == right.id:
            raise Rejected("找不到要连起来的记忆")
        if left.state in _GONE or right.state in _GONE:
            raise Rejected("那条记忆已经淡忘了")
        if swap:
            left, right = right, left
        self._join(left, left.anchor_id, right.anchor_id, kind)
        self._evidence(kind, right)
        self._accept("link", left.id, f"{_shown(left)} → {_shown(right)}", [])

    def _op_merge(self, raw: dict) -> None:
        keep = self._target(raw, "keep")
        drops: list[Fiber] = []
        for value in _items(raw.get("drop")):
            fiber = self._handle(value)
            if fiber is None or fiber.id == keep.id or fiber.id in {item.id for item in drops}:
                raise Rejected("找不到要合并的记忆")
            if fiber.memory_type == "innate" or fiber.state not in CHANGEABLE_STATES:
                raise Rejected("这条记忆不能合并")
            drops.append(fiber)
        if not drops:
            raise Rejected("没有要合并的记忆")
        statement = clip(raw.get("statement"), STATEMENT_CHARS)
        gist = clip(raw.get("gist"), GIST_CHARS)
        detail = clip(raw.get("detail"), DETAIL_CHARS)
        notes: list[str] = []
        parts = Parts(cues=self._cues(raw.get("cues")))
        self._guard([statement, gist, detail, *parts.cues])
        group = [keep, *drops]
        days = sorted({day for fiber in group for day in fiber.recall_days})
        emotions = [fiber.emotion for fiber in group if fiber.emotion is not None]
        update: dict[str, object] = {
            "recall_count": sum(fiber.recall_count for fiber in group),
            "recall_days": days,
            "strength": max(fiber.strength for fiber in group),
            "importance": max(fiber.importance for fiber in group),
            "stage": max((fiber.stage for fiber in group), key=lambda stage: _STAGE_RANK[stage]),
            "emotion": max(emotions, key=lambda item: item.intensity) if emotions else None,
            "updated_at": self.stamp,
        }
        if statement:
            update.update(
                statement=statement, gist=gist or statement[:GIST_CHARS], detail=detail
            )
        merged = keep.model_copy(update=update)
        merged = merged.model_copy(update={"detail_level": lowest_level(merged)})
        self.store.save_fiber(merged)
        for fiber in drops:
            self._rehome(merged, fiber)
            self.store.add_cues(merged.id, fiber.cues)
            self._set_state(fiber, "merged")
        self.store.add_cues(merged.id, parts.cues)
        self.outcome.changed.append(merged.id)
        self._accept("merge", merged.id, _shown(merged), notes)

    # checks

    def _draft(
        self,
        raw: object,
        *,
        base: Fiber | None = None,
        default_type: str | None = None,
    ) -> Draft:
        if not isinstance(raw, dict):
            raise Rejected("缺少新记忆的内容")
        phase = self.ctx.phase
        notes: list[str] = []
        memory_type = str(raw.get("type") or default_type or (base.memory_type if base else ""))
        memory_type = "innate" if phase == "birth" else memory_type.strip()
        if memory_type not in MEMORY_TYPES:
            raise Rejected("不认识的记忆类型")
        if phase != "birth" and memory_type == "innate":
            raise Rejected("天生记忆只来自身份信")
        if phase == "note" and memory_type in SLEEP_ONLY_TYPES:
            raise Rejected("这类记忆在睡眠时才形成")
        statement = clip(raw.get("statement"), STATEMENT_CHARS)
        if not statement:
            raise Rejected("缺少一句话的内容")
        about = clip(raw.get("about"), MAX_NAME_CHARS)
        if not about:
            about = self._about_name(base) if base is not None else self._default_about(memory_type)
        evidence = clip(raw.get("evidence"), DETAIL_CHARS)
        source = self._source(memory_type, str(raw.get("source") or ""), evidence, about, notes)
        default_importance = 8 if phase == "birth" else DEFAULT_IMPORTANCE
        importance = _int(raw.get("importance"), default_importance, 1, 10)
        emotion = self._emotion(raw.get("emotion"))
        start, end = self._span(raw.get("occurred"))
        if memory_type == "session" and self.ctx.session_span is not None:
            start, end = self.ctx.session_span
        due_at = self._moment(raw.get("due"))
        trigger = clip(raw.get("trigger"), TRIGGER_CHARS)
        if memory_type == "plan" and not (due_at or trigger):
            raise Rejected("打算要写明时间或触发条件")
        confidence = None
        if source in INFERRED_SOURCES:
            confidence = _float(
                raw.get("confidence"), INFERRED_CONFIDENCE, 0.05, INFERRED_CONFIDENCE_CAP
            )
        draft = Draft(
            memory_type=memory_type,
            about=about,
            source=source,
            statement=statement,
            detail=clip(raw.get("detail"), DETAIL_CHARS) or evidence,
            gist=clip(raw.get("gist"), GIST_CHARS) or statement[:GIST_CHARS],
            evidence=evidence,
            importance=importance,
            emotion=emotion,
            confidence=confidence,
            occurred=(start, end),
            due_at=due_at,
            trigger=trigger,
            valid_until=self._moment(raw.get("valid_until")),
            parts=self._parts(raw, notes),
            notes=notes,
        )
        self._guard(
            [
                draft.statement,
                draft.detail,
                draft.gist,
                draft.evidence,
                draft.trigger,
                draft.about,
                emotion.label if emotion else "",
                emotion.who if emotion else "",
                *_part_texts(draft.parts),
            ]
        )
        return draft

    def _source(
        self, memory_type: str, claimed: str, evidence: str, about: str, notes: list[str]
    ) -> str:
        phase = self.ctx.phase
        claimed = claimed.strip()
        if phase == "birth":
            if not contains_quote(self.ctx.letter, evidence):
                raise Rejected("天生记忆要能在身份信里找到原文")
            return "innate"
        if phase == "sleep":
            if claimed == "shared" and memory_type in {"session", "event"}:
                return "shared"
            if claimed and claimed != "reflection":
                notes.append("睡眠时的整理记为归纳")
            return "reflection"
        if claimed not in {"user", "self", "shared", "inference"}:
            if claimed:
                notes.append("来源记为推断")
            return "inference"
        heard = contains_quote(self.ctx.user_text, evidence)
        said = contains_quote(self.ctx.reply_text, evidence)
        if claimed == "user" and not heard:
            notes.append("原话对不上，记为推断")
            return "inference"
        if claimed == "self":
            if not said:
                notes.append("她的原话对不上，记为推断")
                return "inference"
            if self._is_user(about):
                notes.append("她说的关于他的话只算推断")
                return "inference"
        if claimed == "shared" and not (heard or said):
            notes.append("原话对不上，记为推断")
            return "inference"
        return claimed

    def _parts(self, raw: dict, notes: list[str]) -> Parts:
        parts = Parts(cues=self._cues(raw.get("cues")))
        for item in _items(raw.get("nodes"))[:MAX_NODES]:
            if isinstance(item, str):
                item = {"name": item}
            if not isinstance(item, dict):
                continue
            name = clip(item.get("name"), MAX_NAME_CHARS)
            if not name or (name in STOP_TERMS and not _pronoun(name)):
                continue
            kind = str(item.get("kind") or "topic").strip()
            aliases = [clip(alias, MAX_NAME_CHARS) for alias in _items(item.get("aliases"))]
            aliases = [
                alias
                for alias in aliases[:MAX_ALIASES]
                if alias and alias not in STOP_TERMS and key_of(alias) != key_of(name)
            ]
            parts.nodes.append((name, kind if kind in NODE_KINDS else "topic", aliases))
        for item in _items(raw.get("relations"))[:MAX_RELATIONS]:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "").strip()
            left = clip(item.get("source"), MAX_NAME_CHARS)
            right = clip(item.get("target"), MAX_NAME_CHARS)
            if kind not in NODE_RELATIONS or not left or not right or key_of(left) == key_of(right):
                notes.append("忽略了一条不认识的关系")
                continue
            if left in PRONOUNS_BOTH or right in PRONOUNS_BOTH:
                notes.append("关系两端要写成具体的人")
                continue
            parts.relations.append((left, kind, right, clip(item.get("label"), LABEL_CHARS)))
        for item in _items(raw.get("links"))[:MAX_LINKS]:
            if not isinstance(item, dict):
                continue
            kind, swap = _canonical(item.get("type"))
            target = self._handle(item.get("target"))
            if kind not in MEMORY_LINKS or target is None or target.state in _GONE:
                notes.append("忽略了一条联系")
                continue
            parts.links.append((kind, target.id, swap))
        return parts

    def _cues(self, values: object) -> list[str]:
        cues: list[str] = []
        for value in _items(values)[:MAX_CUES]:
            term = clip(value, MAX_TERM_CHARS + 1)
            if not term or len(term) > MAX_TERM_CHARS or term in STOP_TERMS or term in cues:
                continue
            cues.append(term)
        return cues

    def _emotion(self, raw: object) -> Emotion | None:
        if not isinstance(raw, dict):
            return None
        label = clip(raw.get("label"), LABEL_CHARS)
        if not label:
            return None
        who = self._display(clip(raw.get("who"), MAX_NAME_CHARS) or self._name(self.user_id))
        return Emotion(who=who, label=label, intensity=_float(raw.get("intensity"), 0.5, 0.0, 1.0))

    def _span(self, value: object) -> tuple[str | None, str | None]:
        if isinstance(value, dict):
            start = self._moment(value.get("start"))
            end = self._moment(value.get("end"), end_of_day=True) or start
            return start, end
        if not isinstance(value, str) or not value.strip():
            return None, None
        start = self._moment(value)
        return start, self._moment(value, end_of_day=True) or start

    def _moment(self, value: object, *, end_of_day: bool = False) -> str | None:
        moment = parse_local(value, self.ctx.tz)
        if moment is None:
            return None
        if end_of_day and isinstance(value, str) and ":" not in value:
            moment = moment + timedelta(days=1)
        return dump_time(moment)

    def _guard(self, texts: list[str]) -> None:
        for text in texts:
            if text and has_secret(text, self.ctx.api_key):
                raise Rejected("含有密钥形态的内容")

    def _target(
        self, raw: dict, key: str = "target", *, states: frozenset[str] = CHANGEABLE_STATES
    ) -> Fiber:
        fiber = self._handle(raw.get(key))
        if fiber is None:
            raise Rejected("找不到要改的那条记忆")
        if fiber.memory_type == "innate":
            raise Rejected("天生记忆不能改")
        if fiber.state not in states:
            raise Rejected("这条记忆现在不能这样改")
        return fiber

    def _handle(self, value: object) -> Fiber | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        if text.isdigit():
            text = f"m{text}"
        fiber_id = self.ctx.handles.get(text)
        return None if fiber_id is None else self.store.fiber(fiber_id)

    # writes

    def _create(self, draft: Draft) -> Fiber:
        fiber_id = new_id()
        innate = draft.memory_type == "innate"
        anchor = self.store.ensure_neuron(ANCHOR_KIND, fiber_id)
        about, people = self._about(draft.about, innate, draft.parts)
        intensity = draft.emotion.intensity if draft.emotion else 0.0
        fiber = Fiber(
            id=fiber_id,
            anchor_id=anchor.id,
            memory_type=draft.memory_type,
            about=about,
            statement=draft.statement,
            detail=draft.detail,
            gist=draft.gist,
            evidence=draft.evidence,
            source=draft.source,
            importance=draft.importance,
            emotion=draft.emotion,
            confidence=draft.confidence,
            strength=1.0 if innate else initial_strength(draft.importance, intensity),
            stage="settled" if innate else "fresh",
            occurred_start=draft.occurred[0],
            occurred_end=draft.occurred[1],
            due_at=draft.due_at,
            trigger=draft.trigger,
            valid_until=draft.valid_until,
            session_id=self.ctx.session_id,
            created_at=self.stamp,
            updated_at=self.stamp,
            state_changed_at=self.stamp,
            settled_at=self.stamp,
            neuron_ids=[anchor.id],
        )
        fiber = fiber.model_copy(update={"detail_level": lowest_level(fiber)})
        self.store.insert_fiber(fiber)
        for person in people:
            self._join(fiber, anchor.id, person, "involves", innate=innate)
        self._attach(fiber, draft.parts or Parts(), draft.memory_type, occurred=draft.occurred[0])
        if draft.emotion is not None:
            emotion = self.store.ensure_neuron("emotion", draft.emotion.label)
            self._join(fiber, anchor.id, emotion.id, "felt", label=draft.emotion.who, innate=innate)
        self.outcome.created.append(fiber.id)
        return fiber

    def _attach(
        self, fiber: Fiber, parts: Parts, memory_type: str, *, occurred: str | None = None
    ) -> None:
        innate = memory_type == "innate"
        found: dict[str, str] = {}
        for name, kind, aliases in parts.nodes:
            node_id = self._node(name, kind, aliases, innate)
            if node_id is None:
                continue
            found[key_of(name)] = node_id
            node = self.store.neuron(node_id)
            element = "involves"
            if node is not None and node.kind == "place" and memory_type in _PLACE_TYPES:
                element = "located_at"
            self._join(fiber, fiber.anchor_id, node_id, element, innate=innate)
        for left_name, kind, right_name, label in parts.relations:
            left = found.get(key_of(left_name)) or self._node(left_name, None, [], innate)
            right = found.get(key_of(right_name)) or self._node(right_name, None, [], innate)
            if left is None or right is None or left == right:
                continue
            self.store.add_members(fiber.id, [left, right])
            self._join(fiber, left, right, kind, label=label, innate=innate)
        if occurred:
            day = local_day(load_time(occurred), self.ctx.tz)
            node = self.store.ensure_neuron("time", day)
            self._join(fiber, fiber.anchor_id, node.id, "happened_on", innate=innate)
        for kind, target_id, swap in parts.links:
            target = self.store.fiber(target_id)
            if target is None or target.id == fiber.id:
                continue
            left, right = (target, fiber) if swap else (fiber, target)
            self._join(fiber, left.anchor_id, right.anchor_id, kind)
            self._evidence(kind, right)
        self.store.add_cues(fiber.id, parts.cues)

    def _join(
        self,
        owner: Fiber,
        source_id: str,
        target_id: str,
        kind: str,
        *,
        label: str = "",
        innate: bool = False,
    ) -> None:
        if source_id == target_id:
            return
        synapse, created = self.store.add_synapse(
            source_id, target_id, kind, base_weight=DEFAULT_LINK_WEIGHT, label=label, innate=innate
        )
        if not created and not synapse.innate:
            self.store.save_synapse(hebbian(synapse, self.now))
        self.store.add_members(owner.id, [source_id, target_id])
        self.store.link_fiber_synapse(owner.id, synapse.id)

    def _rehome(self, keep: Fiber, drop: Fiber) -> None:
        """Move what a merged memory was connected to onto the one that stays."""
        for synapse in self.store.synapses():
            ends = (synapse.source_id, synapse.target_id)
            if drop.anchor_id not in ends or keep.anchor_id in ends:
                continue
            left = keep.anchor_id if synapse.source_id == drop.anchor_id else synapse.source_id
            right = keep.anchor_id if synapse.target_id == drop.anchor_id else synapse.target_id
            self._join(keep, left, right, synapse.type, label=synapse.label)

    def _set_state(self, fiber: Fiber, state: str, **extra: object) -> None:
        current = self.store.fiber(fiber.id) or fiber
        update: dict[str, object] = {
            "state": state,
            "state_changed_at": self.stamp,
            "updated_at": self.stamp,
            **extra,
        }
        self.store.save_fiber(current.model_copy(update=update))
        self.outcome.changed.append(fiber.id)

    def _evidence(self, kind: str, fiber: Fiber) -> None:
        if kind not in {"supports", "opposes"}:
            return
        current = self.store.fiber(fiber.id)
        if current is None or current.source not in INFERRED_SOURCES:
            return
        value = current.confidence if current.confidence is not None else INFERRED_CONFIDENCE
        if kind == "supports":
            value = min(INFERRED_CONFIDENCE_CAP, value + EVIDENCE_FOR_STEP * (1.0 - value))
        else:
            value = value * EVIDENCE_AGAINST_SCALE
        self.store.save_fiber(current.model_copy(update={"confidence": value}))

    def _trace_suppression(self) -> None:
        user = self._name(self.user_id)
        me = self._name(self.self_id)
        start, end = self._span(local_day(self.now, self.ctx.tz))
        statement = f"{user}让{me}忘掉了一件事"
        draft = Draft(
            memory_type="event",
            about=user,
            source="shared",
            statement=statement,
            gist=statement[:GIST_CHARS],
            importance=3,
            occurred=(start, end),
            parts=Parts(cues=["忘掉", "忘记"]),
        )
        fiber = self._create(draft)
        self.store.log(self.ctx.phase, "add", "accepted", fiber_id=fiber.id, label=statement)

    # names

    def _about(self, name: str, innate: bool, parts: Parts | None) -> tuple[str, list[str]]:
        if name in PRONOUNS_BOTH:
            return "both", [self.user_id, self.self_id]
        kind = None
        for node_name, node_kind, _aliases in parts.nodes if parts else []:
            if key_of(node_name) == key_of(name):
                kind = node_kind
        node_id = self._node(name, kind, [], innate)
        if node_id is None:
            return self.user_id, [self.user_id]
        return node_id, [node_id]

    def _node(self, name: str, kind: str | None, aliases: list[str], innate: bool) -> str | None:
        if name in PRONOUNS_BOTH:
            return None
        if name in PRONOUNS_SELF:
            node_id = self.self_id
        elif name in PRONOUNS_USER:
            node_id = self.user_id
        else:
            found = self.store.find_nodes(name)
            if found:
                same = [node for node in found if kind is not None and node.kind == kind]
                node = (same or found)[0]
                if not same and kind not in {None, "topic"} and node.kind == "topic":
                    node = self.store.set_kind(node.id, kind) or node
            elif name in STOP_TERMS:
                return None
            else:
                node = self.store.ensure_neuron(kind or "topic", name, innate=innate)
            if innate and not node.innate:
                self.store.ensure_neuron(node.kind, node.name, innate=True)
            node_id = node.id
        for alias in aliases:
            self.store.add_alias(node_id, alias)
        return node_id

    def _is_user(self, name: str) -> bool:
        if name in PRONOUNS_USER:
            return True
        return any(node.id == self.user_id for node in self.store.find_nodes(name))

    def _display(self, name: str) -> str:
        if name in PRONOUNS_SELF:
            return self._name(self.self_id)
        if name in PRONOUNS_USER or name == "他":
            return self._name(self.user_id)
        return name

    def _name(self, neuron_id: str) -> str:
        neuron = self.store.neuron(neuron_id)
        return neuron.name if neuron is not None else ""

    def _about_name(self, fiber: Fiber) -> str:
        if fiber.about == "both":
            return "我们"
        return self._name(fiber.about) or self._name(self.user_id)

    def _default_about(self, memory_type: str) -> str:
        if self.ctx.phase == "birth" or memory_type == "self":
            return self._name(self.self_id)
        if memory_type == "session":
            return "我们"
        return self._name(self.user_id)

    # journal

    def _accept(self, op: str, fiber_id: str | None, label: str, notes: list[str]) -> None:
        reason = "；".join(dict.fromkeys(notes))
        shown, _ = mask_secrets(label, self.ctx.api_key)
        status = "adjusted" if reason else "accepted"
        self.store.log(
            self.ctx.phase, op, status, fiber_id=fiber_id, label=shown[:80], reason=reason
        )
        suffix = f"（{reason}）" if reason else ""
        self.outcome.lines.append(f"{OP_LABEL.get(op, op)}：{shown[:80]}{suffix}")

    def _reject(self, op: str, label: str, reason: str) -> None:
        shown, _ = mask_secrets(label, self.ctx.api_key)
        self.store.log(self.ctx.phase, op, "rejected", label=shown[:80], reason=reason)
        self.outcome.rejected += 1
        self.outcome.lines.append(f"没有采纳{OP_LABEL.get(op, op)}：{shown[:40]}（{reason}）")


def _canonical(value: object) -> tuple[str, bool]:
    kind = str(value or "").strip()
    if kind in RELATION_ALIASES:
        return RELATION_ALIASES[kind]
    return kind, False


def _pronoun(name: str) -> bool:
    return name in PRONOUNS_SELF or name in PRONOUNS_USER or name in PRONOUNS_BOTH


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _int(value: object, default: int, low: int, high: int) -> int:
    try:
        number = int(float(str(value)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _float(value: object, default: float, low: float, high: float) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return default
    if number != number:
        return default
    return max(low, min(high, number))


def _part_texts(parts: Parts | None) -> list[str]:
    if parts is None:
        return []
    texts: list[str] = list(parts.cues)
    for name, _kind, aliases in parts.nodes:
        texts.append(name)
        texts.extend(aliases)
    for left, _kind, right, label in parts.relations:
        texts.extend((left, right, label))
    return texts


def _has_parts(parts: Parts) -> bool:
    return bool(parts.nodes or parts.relations or parts.cues or parts.links)


def _shown(fiber: Fiber) -> str:
    return fiber.statement or fiber.gist or MEMORY_TYPES.get(fiber.memory_type, "")


def _label(raw: object) -> str:
    if not isinstance(raw, dict):
        return ""
    inner = raw.get("with") if isinstance(raw.get("with"), dict) else {}
    for value in (raw.get("statement"), inner.get("statement"), raw.get("target"), raw.get("keep")):
        if value:
            return str(value)[:80]
    return ""
