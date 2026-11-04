"""Closed Chinese rules. Punctuation sorts clauses; it does not decide the memory."""

from __future__ import annotations

import re

from dylan.memory.encode import Draft
from dylan.memory.lexicon_zh import find_time_words

GREETINGS = frozenset({"你好", "在吗", "谢谢", "好的", "嗯"})
_NAME = re.compile(r"我(?:叫|是)([\u4e00-\u9fffA-Za-z0-9]{1,16})")
_PLACE = re.compile(r"在([\u4e00-\u9fff]{2,8})")
_EMOTIONS = ("高兴", "开心", "难过", "生气", "害怕", "紧张", "委屈", "焦虑")
_FORGET = ("忘掉", "忘记我说过", "别记")
_EDGE = " ，,。！!？?；;～~…"
_ASK = ("是不是", "对不对", "有没有", "是谁", "叫什么", "叫谁")


def extract_rules(text: str) -> tuple[list[Draft], list[str]]:
    raw = text.strip()
    if not raw:
        return [], []
    forgets = _forget_fragments(raw)
    if forgets:
        return [], forgets
    kept = [clause for clause in _clauses(raw) if not _discardable(clause)]
    if not kept:
        return [], []
    drafts = [draft for draft in (_draft(_span(group)) for group in _group(kept)) if draft]
    _relate_turn(drafts)
    return drafts, []


def model_summary_allowed(summary: str) -> bool:
    """Drop a model item that still carries a greeting or a question."""
    clauses = _clauses(summary.strip())
    if not clauses:
        return False
    return not any(_discardable(clause) for clause in clauses)


def _clauses(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []

    def flush(asking: bool) -> None:
        piece = "".join(buf).strip()
        buf.clear()
        if piece:
            parts.append(piece + "？" if asking else piece)

    for char in text:
        if char in "，,。！!；;～~\n":
            flush(False)
            continue
        if char in "?？":
            flush(True)
            continue
        buf.append(char)
    flush(False)
    return parts


def _span(group: list[str]) -> str:
    if len(group) == 1:
        return group[0]
    return "，".join(group)


def _group(clauses: list[str]) -> list[list[str]]:
    """Bind a cause, an order, or a revision to its neighbor. Leave other facts apart."""
    groups: list[list[str]] = []
    index = 0
    while index < len(clauses):
        kind = _binder(clauses[index])
        nxt = index + 1 < len(clauses)
        if kind == "cause":
            leading = clauses[index].startswith("因为")
            next_continues = nxt and _binder(clauses[index + 1]) == "backward"
            if leading and nxt and not next_continues:
                groups.append([clauses[index], clauses[index + 1]])
                index += 2
                continue
            if groups:
                groups[-1].append(clauses[index])
                index += 1
                continue
            if nxt:
                groups.append([clauses[index], clauses[index + 1]])
                index += 2
                continue
        if kind == "forward" and nxt:
            groups.append([clauses[index], clauses[index + 1]])
            index += 2
            continue
        if kind in {"backward", "forward"} and groups:
            groups[-1].append(clauses[index])
            index += 1
            continue
        if kind == "backward" and nxt:
            groups.append([clauses[index], clauses[index + 1]])
            index += 2
            continue
        groups.append([clauses[index]])
        index += 1
    return groups


def _binder(clause: str) -> str | None:
    if "说错了" in clause or "不是这样" in clause or "改成" in clause or _dropped(clause):
        return "forward"
    if "因为" in clause:
        return "cause"
    if "所以" in clause or any(word in clause for word in ("然后", "之后", "之前")):
        return "backward"
    return None


def _discardable(clause: str) -> bool:
    core = clause.strip(_EDGE)
    if not core or core in GREETINGS:
        return True
    return _question(clause.strip())


def _draft(raw: str) -> Draft | None:
    links: list[tuple[str, str, str]] = []
    neurons: list[tuple[str, str]] = [("concept", raw)]
    memory_type = "fact"
    supersede: str | None = None
    contradicts_previous = False
    tags: list[str] = []

    named = _NAME.search(raw)
    if named and named.group(1) not in {"谁", "什么"}:
        neurons.append(("entity", named.group(1)))
        memory_type = "fact"

    if any(word in raw for word in ("不可以", "别再", "不允许")):
        memory_type = "boundary"
    elif any(word in raw for word in ("以后", "回答我时", "记得用")):
        memory_type = "instruction"
    elif any(word in raw for word in ("待办", "记着要", "提醒我还有")):
        memory_type = "todo"
    elif any(word in raw for word in ("报错", "失败了", "出错")):
        memory_type = "error"
    elif any(word in raw for word in ("流程是", "每次都是先")):
        memory_type = "workflow"
    elif any(word in raw for word in ("决定", "改成")) or _dropped(raw):
        memory_type = "decision"
        if "改成" in raw or _dropped(raw):
            supersede = "evolves_from"
    elif any(word in raw for word in ("喜欢", "偏好", "讨厌", "不喜欢")):
        memory_type = "preference"

    for word in find_time_words(raw):
        neurons.append(("time", word))
        tags.append(word)
    links.extend(_relations(raw))
    place = _PLACE.search(raw)
    if place and place.group(1) not in {"吗", "这里"}:
        neurons.append(("concept", place.group(1)))
        links.append((raw, place.group(1), "at_location"))
    for emotion in _EMOTIONS:
        if emotion in raw:
            neurons.append(("emotion", emotion))
            links.append((raw, emotion, "felt"))
            break
    if any(word in raw for word in ("说错了", "不是这样")):
        contradicts_previous = True

    ordered = _ordered_parts(raw)
    if len(ordered) >= 2:
        neurons = [(kind, content) for kind, content in neurons if content != raw]
        for part in ordered:
            neurons.append(("concept", part))
        for left, right in zip(ordered, ordered[1:]):
            links.append((left, right, "before"))
        if memory_type == "fact" and "流程是" not in raw:
            memory_type = "episode"

    concepts = [content for kind, content in neurons if kind in {"concept", "entity"}]
    if len(concepts) >= 2:
        for left, right in zip(concepts, concepts[1:]):
            links.append((left, right, "co_occurs"))

    if memory_type == "fact" and not _substantive(raw):
        return None
    return Draft(
        memory_type=memory_type,
        summary=raw,
        body=raw,
        neurons=_unique(neurons),
        links=_unique_links(links),
        tags=tags,
        supersede_previous=supersede,
        contradicts_previous=contradicts_previous,
    )


def _relate_turn(drafts: list[Draft]) -> None:
    for earlier, later in zip(drafts, drafts[1:]):
        left, right = earlier.summary, later.summary
        if not left or not right or left == right:
            continue
        link = (left, right, "co_occurs")
        if link not in later.links:
            later.links.append(link)


def _question(text: str) -> bool:
    stripped = text.strip(_EDGE)
    if not stripped:
        return False
    if text.endswith(("?", "？", "吗")) or stripped.endswith(("?", "？", "吗")):
        return True
    if any(phrase in stripped for phrase in _ASK):
        return True
    if stripped.endswith("呢") and _soft_question(stripped):
        return True
    tails = ("什么", "谁", "哪", "哪里", "哪些", "哪儿", "怎么", "怎样", "如何", "多少")
    if stripped.endswith(tails):
        return True
    return stripped.endswith("么") and any(word in stripped for word in ("什么", "怎么", "哪"))


def _soft_question(text: str) -> bool:
    if text.startswith("你"):
        return True
    return any(word in text for word in ("觉得", "什么", "怎么", "哪", "谁"))


def _forget_fragments(text: str) -> list[str]:
    found: list[str] = []
    for marker in _FORGET:
        if marker not in text:
            continue
        fragment = text.split(marker, 1)[1].strip(" ：:，,。！？?吗")
        if fragment:
            found.append(fragment)
    return found


def _dropped(text: str) -> bool:
    return "不用" in text and "了" in text


def _relations(text: str) -> list[tuple[str, str, str]]:
    if "因为" in text:
        effect, cause = text.split("因为", 1)
        effect, cause = _clean(effect), _clean(cause)
        if "所以" in cause:
            cause, so_effect = _split_cause(cause)
            effect = effect or so_effect
        elif not effect and cause:
            cause, effect = _split_cause(cause)
        if effect and cause:
            return [(effect, cause, "caused_by")]
        return []
    if "所以" in text:
        cause, effect = text.split("所以", 1)
        cause, effect = _clean(cause), _clean(effect)
        if cause and effect:
            return [(effect, cause, "caused_by")]
    return []


def _split_cause(cause: str) -> tuple[str, str]:
    if "所以" in cause:
        left, right = cause.split("所以", 1)
        return _clean(left), _clean(right)
    for sep in ("，", ",", "；", ";"):
        if sep in cause:
            left, right = cause.split(sep, 1)
            return _clean(left), _clean(right)
    return cause, ""


def _ordered_parts(text: str) -> list[str]:
    if "之前" in text and not any(marker in text for marker in ("然后", "之后")):
        parts = [_clean(part) for part in text.split("之前")]
        parts = [part for part in parts if part]
        if len(parts) >= 2:
            parts.reverse()
            return parts
        return []
    if not any(marker in text for marker in ("然后", "之后")):
        return []
    pieces = [text]
    for marker in ("然后", "之后"):
        expanded: list[str] = []
        for piece in pieces:
            expanded.extend(piece.split(marker))
        pieces = expanded
    return [part for part in (_clean(piece) for piece in pieces) if part]


def _clean(text: str) -> str:
    return text.strip(_EDGE)


def _substantive(text: str) -> bool:
    return len(text.strip()) >= 2


def _unique(neurons: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    ordered: list[tuple[str, str]] = []
    for item in neurons:
        if not item[1] or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _unique_links(links: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    ordered: list[tuple[str, str, str]] = []
    for item in links:
        if item[0] == item[1] or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
