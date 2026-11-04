"""Idempotent fiber decay and synapse effective weight."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from dylan.clock import days_between, dump_time, hours_between, load_time
from dylan.memory.constants import (
    HOT_FLOOR,
    LAMBDA,
    SEMANTIC_FLOOR,
    SEMANTIC_LAMBDA_SCALE,
    SYNAPSE_FLOOR_BASE,
    SYNAPSE_FLOOR_CAP,
    SYNAPSE_FLOOR_STEP,
    SYNAPSE_HALF_LIFE_GROWTH,
    SYNAPSE_HALF_LIFE_HOURS,
    TIER_MULTIPLIER,
    UNKNOWN_LAMBDA,
)
from dylan.memory.model import Fiber, Synapse


def synapse_factor(hours: float, rehearsal_count: int) -> float:
    half_life = SYNAPSE_HALF_LIFE_HOURS * (1.0 + SYNAPSE_HALF_LIFE_GROWTH * rehearsal_count)
    spread = half_life / 2.0
    raw = 1.0 / (1.0 + math.exp((hours - half_life) / spread))
    floor = SYNAPSE_FLOOR_BASE + min(SYNAPSE_FLOOR_CAP, SYNAPSE_FLOOR_STEP * rehearsal_count)
    return max(floor, raw)


def effective_weight(synapse: Synapse, now: datetime) -> float:
    started = load_time(synapse.last_activated_at or synapse.created_at)
    hours = max(0.0, hours_between(started, now))
    factor = synapse_factor(hours, synapse.rehearsal_count)
    return min(1.0, max(0.0, synapse.base_weight * factor))


def _floor(fiber: Fiber) -> float:
    floor = 0.0
    if fiber.tier == "hot":
        floor = max(floor, HOT_FLOOR)
    if fiber.stage == "semantic":
        floor = max(floor, SEMANTIC_FLOOR)
    return floor


def _skips(fiber: Fiber) -> bool:
    return (
        fiber.memory_type == "identity"
        or fiber.pinned
        or fiber.state == "frozen"
    )


def decay_fiber(fiber: Fiber, now: datetime) -> Fiber:
    cursor = load_time(fiber.decay_cursor)
    if _skips(fiber):
        return fiber.model_copy(update={"decay_cursor": dump_time(now)})
    delta = max(0.0, days_between(cursor, now))
    if delta == 0:
        return fiber
    lam = LAMBDA.get(fiber.memory_type, UNKNOWN_LAMBDA)
    if lam is None:
        return fiber.model_copy(update={"decay_cursor": dump_time(now)})
    if fiber.stage == "semantic":
        lam *= SEMANTIC_LAMBDA_SCALE
    stability = 1.0 + math.log(1.0 + fiber.rehearsal_count)
    multiplier = TIER_MULTIPLIER.get(fiber.tier, 1.0)
    factor = math.exp(-lam * multiplier * delta / stability)
    conductivity = max(_floor(fiber), fiber.conductivity * factor)
    return fiber.model_copy(
        update={"conductivity": conductivity, "decay_cursor": dump_time(now)}
    )


def apply_decay(store: object) -> None:
    """Settle fiber cursors once. A second call at the same clock does not change strength."""
    from dylan.memory.lifecycle import expire_due

    now = store.clock.now()  # type: ignore[attr-defined]
    with store.transaction():  # type: ignore[attr-defined]
        for fiber in store.fibers():  # type: ignore[attr-defined]
            store.save_fiber(decay_fiber(fiber, now))  # type: ignore[attr-defined]
        store.conn.execute(  # type: ignore[attr-defined]
            "UPDATE meta SET last_decay_at = ? WHERE id = 1",
            (dump_time(now),),
        )
        expire_due(store)  # type: ignore[arg-type]


def expires_on(memory_type: str, created: datetime) -> datetime | None:
    from dylan.memory.constants import EXPIRY_DAYS

    days = EXPIRY_DAYS.get(memory_type)
    if days is None:
        return None
    return created + timedelta(days=days)
