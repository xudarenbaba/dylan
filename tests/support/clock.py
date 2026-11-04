"""Fixed clock for tests: 2026-11-03 20:00 in Shanghai."""

from dylan.clock import FakeClock, load_time

START = "2026-11-03T12:00:00Z"


def fixed_clock() -> FakeClock:
    return FakeClock(load_time(START))
