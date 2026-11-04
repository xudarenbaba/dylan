"""Promote episodic fibers into the working stage."""

from __future__ import annotations

from dylan.memory.constants import WORKING_MIN_DAYS, WORKING_MIN_FREQUENCY
from dylan.memory.model import Fiber


def note_rehearsal(fiber: Fiber, day: str) -> Fiber:
    dates = list(fiber.recall_dates)
    if day not in dates:
        dates.append(day)
    updated = fiber.model_copy(
        update={
            "recall_dates": dates,
            "frequency": fiber.frequency + 1,
            "rehearsal_count": fiber.rehearsal_count + 1,
        }
    )
    return maybe_working(updated)


def maybe_working(fiber: Fiber) -> Fiber:
    if fiber.stage != "episodic":
        return fiber
    if fiber.memory_type == "identity":
        return fiber
    if len(set(fiber.recall_dates)) < WORKING_MIN_DAYS:
        return fiber
    if fiber.frequency < WORKING_MIN_FREQUENCY:
        return fiber
    return fiber.model_copy(update={"stage": "working"})
