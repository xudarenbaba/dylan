"""Prompt order and the two character budgets. len() counts code points."""

from __future__ import annotations

from dylan.dialogue.buffer import Buffer
from dylan.dialogue.thought import Thought
from dylan.memory.model import Fiber

CONSTRAINTS = (
    "回答必须遵守思考记录里的态度。"
    "清楚记得的才可以当作发生过的事。"
    "模糊的只能说有一点印象。"
    "推断必须说是推断，不能说成用户说过。"
    "没有印象就说没有印象，不要用一般知识编成记得的个人事实。"
    "冲突要同时承认两边。"
    "可见回答不使用内部字段名。"
)

_HOT_ORDER = {"identity": 0, "boundary": 1, "instruction": 2}


def pack_hot(entries: list[tuple[str, str]], budget: int) -> str:
    ordered = sorted(entries, key=lambda item: _HOT_ORDER.get(item[0], 9))
    remaining = budget
    chunks: list[str] = []
    for _kind, text in ordered:
        if remaining <= 0 or not text:
            break
        separator = 1 if chunks else 0
        room = remaining - separator
        if room <= 0:
            break
        piece = text[:room]
        chunks.append(piece)
        remaining -= separator + len(piece)
    return "\n".join(chunks)


def pack_recall(items: list[tuple[float, str]], budget: int) -> str:
    kept: list[str] = []
    used = 0
    for _score, text in sorted(items, key=lambda item: item[0], reverse=True):
        if not text:
            continue
        addition = len(text) if not kept else len(text) + 1
        if used + addition > budget:
            continue
        kept.append(text)
        used += addition
    return "\n".join(kept)


def hot_entries(fibers: list[Fiber]) -> list[tuple[str, str]]:
    entries = [
        (fiber.memory_type, fiber.body or fiber.summary)
        for fiber in fibers
        if fiber.state == "active" and fiber.memory_type in _HOT_ORDER
    ]
    return sorted(entries, key=lambda item: _HOT_ORDER[item[0]])


def build_messages(
    *,
    identity_text: str,
    hot_text: str,
    thought: Thought,
    recall_text: str,
    buffer: Buffer,
    user_text: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": f"{identity_text}\n{CONSTRAINTS}"},
        {"role": "system", "content": f"热层：\n{hot_text}"},
        {
            "role": "system",
            "content": f"思考记录：{thought.model_dump_json()}\n召回：\n{recall_text}",
        },
    ]
    for past_user, past_answer in buffer.turns:
        messages.append({"role": "user", "content": f"刚才的对话\n{past_user}"})
        messages.append({"role": "assistant", "content": past_answer})
    messages.append({"role": "user", "content": user_text})
    return messages
