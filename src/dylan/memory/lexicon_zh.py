"""Closed sets of time-word aliases. These are explicit edges, not embeddings."""

from __future__ import annotations

TIME_GROUPS: dict[str, tuple[str, ...]] = {
    "夜间": ("深夜", "晚上", "夜里", "夜间", "半夜"),
    "早晨": ("早上", "早晨", "上午"),
    "午后": ("下午", "午后"),
}


def time_words() -> tuple[str, ...]:
    words: list[str] = []
    for group in TIME_GROUPS.values():
        words.extend(group)
    return tuple(words)


def find_time_words(text: str) -> list[str]:
    return [word for word in time_words() if word in text]
