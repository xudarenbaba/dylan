"""She decides whether to speak. Declining writes no memory and no made-up day."""

from __future__ import annotations

from dataclasses import dataclass

from dylan.memory.constants import HER_TURN, INITIATIVE_LINE_CHARS
from dylan.memory.store import MemoryStore
from dylan.memory.text import clip


@dataclass(frozen=True)
class Choice:
    """speak is whether she chose to talk. line is None when those words cannot be said."""

    speak: bool
    line: str | None


def accept(proposal: object) -> Choice:
    """Her choice. A false speak keeps her quiet. A bad line is refused."""
    if not isinstance(proposal, dict):
        return Choice(False, None)
    speak = proposal.get("speak")
    if speak is False or speak is None:
        return Choice(False, None)
    if speak is not True:
        return Choice(True, None)
    raw_line = proposal.get("line")
    if not isinstance(raw_line, str):
        return Choice(True, None)
    line = clip(raw_line, INITIATIVE_LINE_CHARS).strip()
    if not line or "〔" in line or "〕" in line:
        return Choice(True, None)
    return Choice(True, line)


def situation(store: MemoryStore, turns: list[tuple[str, str]], limit: int) -> str:
    """What she can weigh. Facts only: her last opening, and this window's lines."""
    rows = store.initiative_rows()
    if not rows:
        earlier = "你还没有先开口过。"
    elif rows[-1]["op"] == "speak":
        label = str(rows[-1]["label"] or "").strip() or "一句"
        earlier = f"你上一句先说的是「{label}」，他还没接。"
    else:
        earlier = "你上一句先说的，他已经接过了。"
    recent = list(turns[-limit:] if limit else [])
    lines = [_said(said, answered) for said, answered in recent]
    body = "\n".join(lines) if lines else "（这个窗口里还没有对话）"
    return f"{earlier}\n\n这个窗口里刚说过的：\n{body}"


def _said(said: str, answered: str) -> str:
    if said == HER_TURN:
        return f"你先说：{answered}"
    return f"他：{said}\n你：{answered}"
