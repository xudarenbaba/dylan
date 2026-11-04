"""One exclusive lock beside the database file."""

from __future__ import annotations

import fcntl
from pathlib import Path

from dylan.errors import LockedBrain


class BrainLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: object | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise LockedBrain() from exc
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        handle.close()  # type: ignore[attr-defined]
        self._handle = None
