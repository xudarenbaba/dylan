"""What she is told before she speaks, writes a note, sleeps, or reads her letter."""

from __future__ import annotations

import json
from datetime import datetime, tzinfo
from pathlib import Path

from dylan.clock import local_stamp
from dylan.memory.constants import (
    MEMORY_LINKS,
    MEMORY_TYPES,
    NODE_KINDS,
    NODE_RELATIONS,
    RELATIONS,
)
from dylan.memory.model import Fiber
from dylan.memory.render import describe

_GUIDES = Path(__file__).with_name("guides")
BIRTH_MARK = "〔出生〕"
NOTE_MARK = "〔记下这一刻〕"
SLEEP_MARK = "〔睡眠整理〕"
RECALLED_HEAD = "此刻想起的事："
NOTHING_RECALLED = "（没有想起什么特别的）"


def _guide(name: str) -> str:
    return (_GUIDES / f"{name}.txt").read_text(encoding="utf-8").strip()


REPLY_RULES = _guide("reply")

_ADD_SHAPE = {
    "op": "add",
    "type": "fact",
    "about": "人名或 我们",
    "statement": "第三人称的一句话",
    "evidence": "原话片段",
    "source": "user",
    "importance": 5,
    "emotion": {"who": "谁", "label": "情绪", "intensity": 0.5},
    "occurred": "YYYY-MM-DD",
    "due": "YYYY-MM-DD HH:MM",
    "trigger": "什么时候想起来问",
    "valid_until": None,
    "confidence": 0.5,
    "nodes": [{"name": "团子", "kind": "animal", "aliases": ["猫"]}],
    "relations": [{"source": "赵旭", "type": "raises", "target": "团子", "label": ""}],
    "links": [{"type": "causes", "target": "m1"}],
    "cues": ["团子", "猫"],
    "gist": "几个字",
}
_NOTE_SHAPE = {
    "ops": [
        _ADD_SHAPE,
        {"op": "reinforce", "target": "m1"},
        {"op": "update", "target": "m2", "statement": "新的说法", "evidence": "原话"},
        {"op": "supersede", "target": "m3", "with": {"statement": "新的情况", "...": "同 add"}},
        {"op": "contradict", "target": "m4", "with": {"statement": "另一种说法"}},
        {"op": "complete", "target": "m5", "with": {"type": "event", "statement": "结果"}},
        {"op": "suppress", "target": "m6"},
        {"op": "link", "source": "m1", "type": "causes", "target": "m2"},
    ],
    "used": ["m1"],
    "mood": {"label": "开心", "intensity": 0.6, "cause": "原因"},
    "summary": "这次聊天到目前为止的梗概",
}
_SLEEP_SHAPE = {
    "ops": [
        {"op": "add", "type": "session", "about": "我们", "statement": "...", "source": "shared"},
        {"op": "merge", "keep": "m1", "drop": ["m2"], "statement": "合并后的说法"},
        {"op": "add", "type": "impression", "statement": "...", "links": [
            {"type": "derived_from", "target": "m3"}
        ]},
    ],
    "mood": {"label": "满足", "intensity": 0.4, "cause": "原因"},
    "summary": "这次聊天的梗概",
}
_BIRTH_SHAPE = {
    "user_name": "写信的人",
    "self_name": "dylan",
    "user_aliases": [],
    "baseline_mood": "开朗",
    "ops": [
        {
            "op": "add",
            "about": "dylan",
            "statement": "第三人称的一句话",
            "evidence": "信里的原文",
            "importance": 8,
            "nodes": [],
            "relations": [],
            "cues": [],
        }
    ],
}


def schema_text() -> str:
    types = "、".join(f"{key}（{label}）" for key, label in MEMORY_TYPES.items() if key != "innate")
    kinds = "、".join(f"{key}（{label}）" for key, label in NODE_KINDS.items())
    relations = "、".join(f"{key}（{RELATIONS[key][0]}）" for key in sorted(NODE_RELATIONS))
    links = "、".join(f"{key}（{RELATIONS[key][0]}）" for key in sorted(MEMORY_LINKS))
    return (
        f"记忆类型：{types}。\n"
        f"节点种类：{kinds}。\n"
        f"人和事物之间的关系 relations：{relations}。\n"
        f"记忆之间的联系 links：{links}。"
    )


def _system(mark: str, guide: str, shape: object) -> dict[str, str]:
    content = f"{mark}\n{_guide(guide)}\n\n{schema_text()}\n\n格式：{_dump(shape)}"
    return {"role": "system", "content": content}


def reply_messages(
    *,
    letter: str,
    awareness: str,
    recalled: str,
    turns: list[tuple[str, str]],
    user_text: str,
) -> list[dict[str, str]]:
    mind = f"{awareness}\n\n{RECALLED_HEAD}\n{recalled or NOTHING_RECALLED}\n\n{REPLY_RULES}"
    messages = [
        {"role": "system", "content": letter.strip()},
        {"role": "system", "content": mind},
    ]
    for said, answered in turns:
        messages.append({"role": "user", "content": said})
        messages.append({"role": "assistant", "content": answered})
    messages.append({"role": "user", "content": user_text})
    return messages


def candidate_lines(
    listed: list[tuple[str, Fiber]], clarity_of: dict[str, str], tz: tzinfo, now: datetime
) -> str:
    lines = []
    for handle, fiber in listed:
        line = describe(fiber, clarity_of.get(fiber.id, "clear"), tz, now)
        lines.append(f"{handle} {line}")
    return "\n".join(lines) or "（没有）"


def note_messages(
    *,
    who: tuple[str, str],
    now: datetime,
    tz: tzinfo,
    recent: list[tuple[str, str]],
    user_text: str,
    reply_text: str,
    candidates: str,
    summary: str,
) -> list[dict[str, str]]:
    user_name, self_name = who
    earlier = "\n".join(f"他：{said}\n你：{answered}" for said, answered in recent) or "（没有）"
    body = (
        f"现在是 {local_stamp(now, tz)}。他是{user_name}，你是{self_name}。\n"
        f"这次聊天到目前为止：{summary or '（刚开始）'}\n\n"
        f"再往前几轮：\n{earlier}\n\n"
        f"这一轮：\n他：{user_text}\n你：{reply_text}\n\n"
        f"可能相关的旧记忆：\n{candidates}"
    )
    return [_system(NOTE_MARK, "note", _NOTE_SHAPE), {"role": "user", "content": body}]


def sleep_messages(
    *,
    who: tuple[str, str],
    now: datetime,
    tz: tzinfo,
    transcript: str,
    summary: str,
    candidates: str,
) -> list[dict[str, str]]:
    user_name, self_name = who
    body = (
        f"现在是 {local_stamp(now, tz)}。他是{user_name}，你是{self_name}。\n"
        f"这次聊天的梗概：{summary or '（没有）'}\n\n"
        f"这次聊天的原话：\n{transcript or '（原话已经不在了）'}\n\n"
        f"这次新增或改动的记忆，以及相关的旧记忆：\n{candidates}"
    )
    return [_system(SLEEP_MARK, "sleep", _SLEEP_SHAPE), {"role": "user", "content": body}]


def birth_messages(letter: str) -> list[dict[str, str]]:
    return [
        _system(BIRTH_MARK, "birth", _BIRTH_SHAPE),
        {"role": "user", "content": letter.strip()},
    ]


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)
