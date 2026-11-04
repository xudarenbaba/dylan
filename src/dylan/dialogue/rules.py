"""Closed Chinese rules. A greeting writes nothing. Questions do not become facts."""

from __future__ import annotations

import re

from dylan.memory.encode import Draft
from dylan.memory.lexicon_zh import find_time_words

GREETINGS = frozenset({"你好", "在吗", "谢谢", "好的", "嗯"})
_NAME = re.compile(r"我(?:叫|是)([\u4e00-\u9fffA-Za-z0-9]{1,16})")
_PLACE = re.compile(r"在([\u4e00-\u9fff]{2,8})")
_EMOTIONS = ("高兴", "开心", "难过", "生气", "害怕", "紧张", "委屈", "焦虑")
_FORGET = ("忘掉", "忘记我说过", "别记")


def extract_rules(text: str) -> tuple[list[Draft], list[str]]:
    raw = text.strip()
    if not raw:
        return [], []
    core = raw.strip("。！!？?～~ ")
    if core in GREETINGS:
        return [], []
    forgets = _forget_fragments(raw)
    if forgets:
        return [], forgets
    if _question(raw):
        return [], []

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
        return [], []
    return [
        Draft(
            memory_type=memory_type,
            summary=raw,
            body=raw,
            neurons=_unique(neurons),
            links=_unique_links(links),
            tags=tags,
            supersede_previous=supersede,
            contradicts_previous=contradicts_previous,
        )
    ], []


def _question(text: str) -> bool:
    if text.endswith(("?", "？", "吗")):
        return True
    return text.endswith("么") and any(word in text for word in ("什么", "怎么", "哪"))


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
    links: list[tuple[str, str, str]] = []
    if "因为" in text:
        effect, cause = text.split("因为", 1)
        if effect.strip() and cause.strip():
            links.append((effect.strip(), cause.strip(), "caused_by"))
    elif "所以" in text:
        cause, effect = text.split("所以", 1)
        if cause.strip() and effect.strip():
            links.append((effect.strip(), cause.strip(), "caused_by"))
    return links


def _ordered_parts(text: str) -> list[str]:
    for marker in ("然后", "之后", "之前"):
        if marker in text:
            parts = [part.strip(" ，,。") for part in text.split(marker) if part.strip(" ，,。")]
            if len(parts) >= 2:
                if marker == "之前":
                    parts.reverse()
                return parts
    return []


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
