"""Memory physiology: encoding strength, forgetting, fading detail, settling, clarity."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, tzinfo

from dylan.clock import days_between, dump_time, hours_between, load_time, local_day
from dylan.memory.constants import (
    BASE_STRENGTH,
    CLEAR_STRENGTH,
    DECAY_PER_DAY,
    EMOTION_STABILITY,
    EMOTION_STRENGTH,
    FAMILIAR_COUNT,
    FAMILIAR_DAYS,
    GUESS_CONFIDENCE,
    HEBBIAN_ETA,
    IMPORTANCE_STABILITY_BASE,
    IMPORTANCE_STABILITY_STEP,
    IMPORTANCE_STRENGTH,
    INFERRED_SOURCES,
    LEVEL_THRESHOLDS,
    MOOD_FLOOR,
    MOOD_HALF_LIFE_HOURS,
    OVERDUE_GRACE_DAYS,
    OVERDUE_PLAN_DECAY,
    SETTLED_AGE_DAYS,
    SETTLED_COUNT,
    SETTLED_DAYS,
    SETTLED_STRENGTH,
    SPACING_DAYS,
    SPACING_FLOOR,
    STAGE_DECAY_SCALE,
    STAGE_FLOOR,
    SUPPRESSED_DECAY,
    SYNAPSE_HALF_LIFE_GROWTH,
    SYNAPSE_HALF_LIFE_HOURS,
    VAGUE_STRENGTH,
)
from dylan.memory.model import Fiber, Mood, Synapse


def initial_strength(importance: int, emotion_intensity: float) -> float:
    raw = BASE_STRENGTH + IMPORTANCE_STRENGTH * importance + EMOTION_STRENGTH * emotion_intensity
    return max(0.0, min(1.0, raw))


def stability(fiber: Fiber) -> float:
    rehearsal = 1.0 + math.log(1.0 + fiber.recall_count)
    weight = IMPORTANCE_STABILITY_BASE + IMPORTANCE_STABILITY_STEP * fiber.importance
    feeling = 1.0 + EMOTION_STABILITY * (fiber.emotion.intensity if fiber.emotion else 0.0)
    return max(0.1, rehearsal * weight * feeling)


def daily_decay(fiber: Fiber, now: datetime) -> float:
    if fiber.memory_type == "innate":
        return 0.0
    if fiber.state == "suppressed":
        return SUPPRESSED_DECAY
    if fiber.memory_type == "plan" and fiber.state == "active" and fiber.due_at:
        if now > load_time(fiber.due_at) + timedelta(days=OVERDUE_GRACE_DAYS):
            return OVERDUE_PLAN_DECAY
    return DECAY_PER_DAY.get(fiber.memory_type, 0.05) * STAGE_DECAY_SCALE.get(fiber.stage, 1.0)


def target_level(strength: float) -> int:
    for level, threshold in enumerate(LEVEL_THRESHOLDS):
        if strength >= threshold:
            return level
    return len(LEVEL_THRESHOLDS)


def lowest_level(fiber: Fiber) -> int:
    if fiber.detail:
        return 0
    if fiber.statement:
        return 1
    if fiber.gist:
        return 2
    return 3


def apply_level(fiber: Fiber, level: int) -> Fiber:
    """Detail fades in order. Dropped text never comes back."""
    level = max(level, lowest_level(fiber))
    update: dict[str, object] = {"detail_level": level}
    if level >= 2:
        update["detail"] = ""
        update["evidence"] = ""
    if level >= 3:
        update["statement"] = ""
        update["gist"] = ""
    return fiber.model_copy(update=update)


def settle(fiber: Fiber, now: datetime) -> Fiber:
    """Charge the time since the last settlement once. Calling twice changes nothing."""
    stamp = dump_time(now)
    elapsed = max(0.0, days_between(load_time(fiber.settled_at), now))
    if fiber.memory_type == "innate" or elapsed == 0.0:
        return fiber.model_copy(update={"settled_at": stamp})
    rate = daily_decay(fiber, now)
    strength = fiber.strength
    if rate > 0:
        decayed = strength * math.exp(-rate * elapsed / stability(fiber))
        floor = 0.0 if fiber.state == "suppressed" else STAGE_FLOOR.get(fiber.stage, 0.0)
        strength = decayed if strength <= floor else max(floor, decayed)
    settled = fiber.model_copy(update={"strength": strength, "settled_at": stamp})
    level = max(fiber.detail_level, target_level(strength))
    if fiber.state == "suppressed":
        level = max(level, 2)
    return apply_level(settled, level)


def spacing(fiber: Fiber, now: datetime) -> float:
    last = load_time(fiber.last_recalled_at or fiber.created_at)
    gap = max(0.0, days_between(last, now))
    return SPACING_FLOOR + (1.0 - SPACING_FLOOR) * min(1.0, gap / SPACING_DAYS)


def strengthen(fiber: Fiber, now: datetime, bump: float, tz: tzinfo, *, count: bool) -> Fiber:
    """Recall strengthens. Spaced recall strengthens more than a burst on one day."""
    current = settle(fiber, now)
    if current.memory_type == "innate":
        return current
    strength = min(1.0, current.strength + bump * spacing(current, now))
    update: dict[str, object] = {"strength": strength, "last_recalled_at": dump_time(now)}
    if count:
        days = list(current.recall_days)
        today = local_day(now, tz)
        if today not in days:
            days.append(today)
        update["recall_days"] = days
        update["recall_count"] = current.recall_count + 1
        update["detail_level"] = max(lowest_level(current), current.detail_level - 1)
    return promote(current.model_copy(update=update), now)


def promote(fiber: Fiber, now: datetime) -> Fiber:
    days = len(set(fiber.recall_days))
    if fiber.stage == "fresh" and days >= FAMILIAR_DAYS and fiber.recall_count >= FAMILIAR_COUNT:
        fiber = fiber.model_copy(update={"stage": "familiar"})
    if fiber.stage == "familiar":
        age = days_between(load_time(fiber.created_at), now)
        if (
            age >= SETTLED_AGE_DAYS
            and days >= SETTLED_DAYS
            and fiber.recall_count >= SETTLED_COUNT
            and fiber.strength >= SETTLED_STRENGTH
        ):
            fiber = fiber.model_copy(update={"stage": "settled"})
    return fiber


def clarity(fiber: Fiber, *, conflicted: bool = False) -> str:
    if fiber.memory_type == "innate":
        return "clear"
    if fiber.state == "superseded":
        return "past"
    if conflicted:
        return "conflict"
    if fiber.detail_level >= 3 or fiber.strength < VAGUE_STRENGTH:
        return "trace"
    if fiber.source in INFERRED_SOURCES:
        confidence = fiber.confidence if fiber.confidence is not None else 0.5
        return "guess" if confidence < GUESS_CONFIDENCE else "feeling"
    if fiber.strength >= CLEAR_STRENGTH and fiber.detail_level <= 1:
        return "clear"
    return "vague"


def grown_weight(synapse: Synapse, now: datetime) -> float:
    hours = max(0.0, hours_between(load_time(synapse.last_activated_at), now))
    half_life = SYNAPSE_HALF_LIFE_HOURS * (1.0 + SYNAPSE_HALF_LIFE_GROWTH * synapse.rehearsal_count)
    return synapse.base_weight * math.pow(0.5, hours / half_life)


def link_weight(synapse: Synapse, now: datetime) -> float:
    if synapse.type == "co_recalled" and not synapse.innate:
        return grown_weight(synapse, now)
    return synapse.base_weight


def hebbian(synapse: Synapse, now: datetime) -> Synapse:
    current = grown_weight(synapse, now) if synapse.type == "co_recalled" else synapse.base_weight
    return synapse.model_copy(
        update={
            "base_weight": min(1.0, current + HEBBIAN_ETA * (1.0 - current)),
            "rehearsal_count": synapse.rehearsal_count + 1,
            "last_activated_at": dump_time(now),
        }
    )


def current_mood(mood: Mood | None, now: datetime) -> Mood | None:
    """Feelings fade back toward the baseline."""
    if mood is None:
        return None
    hours = max(0.0, hours_between(load_time(mood.at), now))
    intensity = mood.intensity * math.pow(0.5, hours / MOOD_HALF_LIFE_HOURS)
    if intensity < MOOD_FLOOR:
        return None
    return mood.model_copy(update={"intensity": intensity})
