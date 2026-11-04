"""Injectable clocks, UTC storage and local-time views."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dylan.memory.constants import WEEKDAYS


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


def zone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        if name == "Asia/Shanghai":
            return timezone(timedelta(hours=8))
        return timezone.utc


def local_day(moment: datetime, tz: tzinfo) -> str:
    return moment.astimezone(tz).strftime("%Y-%m-%d")


def local_stamp(moment: datetime, tz: tzinfo) -> str:
    local = moment.astimezone(tz)
    return f"{local:%Y-%m-%d %H:%M} {WEEKDAYS[local.weekday()]}"


def short_day(moment: datetime, tz: tzinfo) -> str:
    local = moment.astimezone(tz)
    return f"{local.year}年{local.month}月{local.day}日"


def short_minute(moment: datetime, tz: tzinfo) -> str:
    local = moment.astimezone(tz)
    if local.hour == 0 and local.minute == 0:
        return short_day(moment, tz)
    return f"{short_day(moment, tz)} {local:%H:%M}"


_LOCAL = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def parse_local(value: object, tz: tzinfo) -> datetime | None:
    """A local date or minute from the model. Stored and compared in UTC."""
    if not isinstance(value, str):
        return None
    match = _LOCAL.match(value.strip())
    if match is None:
        return None
    year, month, day, hour, minute, second = match.groups()
    try:
        local = datetime(
            int(year),
            int(month),
            int(day),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
            tzinfo=tz,
        )
    except ValueError:
        return None
    return local.astimezone(timezone.utc)


def day_bounds(day: str, tz: tzinfo) -> tuple[datetime, datetime] | None:
    start = parse_local(day, tz)
    if start is None:
        return None
    return start, start + timedelta(days=1)


_ISO_DAY = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_MONTH_DAY = re.compile(r"(\d{1,2})月(\d{1,2})[日号]")
_RELATIVE = {"大前天": -3, "前天": -2, "昨天": -1, "今天": 0, "明天": 1, "后天": 2}


def mentioned_days(text: str, now: datetime, tz: tzinfo) -> list[str]:
    """Dates a sentence points at: written dates and the nearby relative words."""
    today = now.astimezone(tz).date()
    found: list[str] = []
    for match in _ISO_DAY.finditer(text):
        found.append(_day_text(int(match[1]), int(match[2]), int(match[3])))
    for match in _MONTH_DAY.finditer(text):
        found.append(_day_text(today.year, int(match[1]), int(match[2])))
    for word, offset in _RELATIVE.items():
        if word in text and not (word == "前天" and "大前天" in text):
            found.append((today + timedelta(days=offset)).isoformat())
    return [day for day in dict.fromkeys(found) if day]


def _day_text(year: int, month: int, day: int) -> str:
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return ""
