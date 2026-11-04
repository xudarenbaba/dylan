"""Recent turns. Overflow is the caller's signal to store an episode."""

from __future__ import annotations


class Buffer:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.turns: list[tuple[str, str]] = []

    def spill(self) -> tuple[str, str] | None:
        if len(self.turns) >= self.limit and self.turns:
            return self.turns[0]
        return None

    def commit(self, user: str, answer: str) -> None:
        if len(self.turns) >= self.limit:
            self.turns.pop(0)
        self.turns.append((user, answer))
