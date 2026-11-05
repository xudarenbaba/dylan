"""Test double. Replies echo what came to mind; JSON answers come from scripted queues."""

from __future__ import annotations

import re
from collections.abc import Iterator

_RECALLED = "此刻想起的事：\n"
_NOTHING = "（没有想起什么特别的）"
_SENTENCE = re.compile(r"[^。！？\n]+")


def request_kind(messages: list[dict[str, str]]) -> str:
    for message in messages:
        content = message.get("content", "")
        if content.startswith("〔出生〕"):
            return "birth"
        if content.startswith("〔睡眠整理〕"):
            return "sleep"
        if content.startswith("〔先开口〕"):
            return "initiative"
        if content.startswith("〔记下这一刻〕"):
            return "note"
    return "note"


class FakeModel:
    def __init__(self, user_name: str = "赵旭") -> None:
        self.user_name = user_name
        self.seen: list[list[dict[str, str]]] = []
        self.json_seen: list[tuple[str, list[dict[str, str]]]] = []
        self.births: list[object] = []
        self.notes: list[object] = []
        self.sleeps: list[object] = []
        self.initiatives: list[object] = []
        self.fail: Exception | None = None
        self.partial: str | None = None
        self.json_fail = False
        self.reply: str | None = None

    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self.seen.append(messages)
        if self.partial is not None:
            yield self.partial
        if self.fail is not None:
            raise self.fail
        yield self.reply if self.reply is not None else render_reply(messages)

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        kind = request_kind(messages)
        self.json_seen.append((kind, messages))
        if self.json_fail:
            raise RuntimeError("json")
        queue = {
            "birth": self.births,
            "note": self.notes,
            "sleep": self.sleeps,
            "initiative": self.initiatives,
        }[kind]
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item  # type: ignore[return-value]
        if kind == "initiative":
            return {"speak": False, "reason": "", "line": ""}
        if kind == "birth":
            return self.default_birth(messages[-1].get("content", ""))
        if kind == "sleep":
            return {
                "ops": [
                    {
                        "op": "add",
                        "type": "session",
                        "about": "我们",
                        "statement": "我们聊了一会儿天",
                        "source": "shared",
                    }
                ],
                "summary": "聊了一会儿天",
                "mood": None,
            }
        return {"ops": [], "used": [], "mood": None, "summary": ""}

    def default_birth(self, letter: str) -> dict[str, object]:
        ops: list[dict[str, object]] = []
        for match in _SENTENCE.finditer(letter):
            sentence = match.group(0).strip("，, ")
            if len(sentence) < 4 or sentence.endswith(("：", ":")):
                continue
            ops.append(
                {
                    "op": "add",
                    "about": "dylan",
                    "statement": sentence,
                    "evidence": sentence,
                    "importance": 8,
                }
            )
            if len(ops) >= 40:
                break
        return {
            "user_name": self.user_name,
            "self_name": "dylan",
            "baseline_mood": "开朗",
            "ops": ops,
        }

    def calls(self, kind: str) -> list[list[dict[str, str]]]:
        return [messages for seen, messages in self.json_seen if seen == kind]


def recalled_block(messages: list[dict[str, str]]) -> str:
    for message in messages:
        content = message.get("content") or ""
        if _RECALLED not in content:
            continue
        block = content.split(_RECALLED, 1)[1].split("\n\n", 1)[0]
        return "" if block.strip() == _NOTHING else block.strip()
    return ""


def render_reply(messages: list[dict[str, str]]) -> str:
    block = recalled_block(messages)
    if not block:
        return "没有印象"
    return "；".join(line.strip() for line in block.splitlines() if line.strip())
