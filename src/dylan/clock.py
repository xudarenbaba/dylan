"""Injectable clocks. Every decay, expiry, stage and habit date reads one clock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        self._moment = moment.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._moment

    def advance(self, *, days: float = 0, hours: float = 0) -> None:
        self._moment = self._moment + timedelta(days=days, hours=hours)


def dump_time(moment: datetime) -> str:
    current = moment.astimezone(timezone.utc).replace(microsecond=0)
    return current.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def days_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86400.0


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0
