"""Fixed clock for acceptance tests."""

from dylan.clock import FakeClock, load_time

START = "2026-11-03T00:00:00Z"


def fixed_clock() -> FakeClock:
    return FakeClock(load_time(START))
