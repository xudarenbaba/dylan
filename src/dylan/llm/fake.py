"""Test double. It answers from the thought record and does not invent memories."""

from __future__ import annotations

import json
from collections.abc import Iterator


class FakeModel:
    def __init__(self) -> None:
        self.seen: list[list[dict[str, str]]] = []
        self.json_seen: list[list[dict[str, str]]] = []
        self.json_items: list[dict[str, object]] = []
        self.fail: Exception | None = None
        self.partial: str | None = None
        self.json_fail = False

    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self.seen.append(messages)
        if self.partial is not None:
            yield self.partial
        if self.fail is not None:
            raise self.fail
        yield render_reply(messages)

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        self.json_seen.append(messages)
        if self.json_fail:
            raise RuntimeError("json")
        return {"items": list(self.json_items)}


def render_reply(messages: list[dict[str, str]]) -> str:
    thought = _read_thought(messages)
    conflicts = thought.get("conflicts") or []
    if conflicts:
        parts = []
        for item in conflicts:
            parts.append(str(item.get("left", "")))
            parts.append(str(item.get("right", "")))
        return "两边都出现过：" + "；".join(part for part in parts if part)
    recalled = thought.get("recalled") or []
    if thought.get("certainty") == "none" or not recalled:
        return "没有印象"
    lines: list[str] = []
    for item in recalled:
        summary = str(item.get("summary", ""))
        attitude = item.get("certainty")
        if attitude == "inferred":
            lines.append(f"我推断{summary}")
        elif attitude == "faint":
            lines.append(f"我有一点印象：{summary}")
        else:
            lines.append(summary)
    return "。".join(lines)


def _read_thought(messages: list[dict[str, str]]) -> dict[str, object]:
    for message in messages:
        content = message.get("content") or ""
        marker = "思考记录："
        if marker not in content:
            continue
        raw = content.split(marker, 1)[1]
        start = raw.find("{")
        if start < 0:
            continue
        try:
            payload, _end = json.JSONDecoder().raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {"certainty": "none", "recalled": [], "conflicts": []}
