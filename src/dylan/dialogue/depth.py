"""Question depth. Cause outranks habit, and both outrank a name question."""

from __future__ import annotations

from dylan.memory.constants import HOPS, TIME_WINDOW_DAYS

_DEPTH_3 = ("为什么", "后来", "原因", "感受", "当时什么感受")
_DEPTH_2 = ("通常", "每次", "习惯")
_DEPTH_0 = ("我叫什么", "你是谁", "你叫什么", "我是谁")


def choose_depth(query: str) -> tuple[int, int, int]:
    if any(word in query for word in _DEPTH_3):
        depth = 3
    elif any(word in query for word in _DEPTH_2):
        depth = 2
    elif any(word in query for word in _DEPTH_0):
        depth = 0
    else:
        depth = 1
    return depth, HOPS[depth], TIME_WINDOW_DAYS[depth]
