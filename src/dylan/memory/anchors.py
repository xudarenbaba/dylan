"""Anchor selection. Time words are time neurons and start at activation 1."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from dylan.clock import load_time
from dylan.memory.constants import ANCHOR_CAP, ANCHOR_JACCARD, SHORT_TEXT
from dylan.memory.jaccard import jaccard
from dylan.memory.model import Fiber, Neuron

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def anchor_cap(neuron: Neuron, workflow_ids: set[str]) -> float:
    if neuron.kind == "time":
        return ANCHOR_CAP["time"]
    if neuron.kind == "entity":
        return ANCHOR_CAP["entity"]
    if neuron.id in workflow_ids or neuron.kind == "episode":
        return ANCHOR_CAP["workflow"] if neuron.id in workflow_ids else ANCHOR_CAP["concept"]
    return ANCHOR_CAP["concept"]


_USER_NAME_QUESTIONS = ("我叫什么", "我是谁")
_NAME_FACT = re.compile(r"我(?:叫|是)([\u4e00-\u9fffA-Za-z0-9]{1,16})")


def name_question_anchors(
    neurons: dict[str, Neuron],
    fibers: list[Fiber],
    query: str,
) -> list[tuple[str, float]]:
    """A name question does not contain the stored name, so depth 0 cannot walk to it."""
    if not any(phrase in query for phrase in _USER_NAME_QUESTIONS):
        return []
    chosen: list[tuple[str, float]] = []
    seen: set[str] = set()
    for fiber in fibers:
        if fiber.state != "active" or fiber.memory_type != "fact":
            continue
        if fiber.provenance.source != "user_input":
            continue
        text = f"{fiber.summary} {fiber.body or ''}"
        for match in _NAME_FACT.finditer(text):
            name = match.group(1)
            if name in {"谁", "什么"} or name.startswith(("什么", "谁", "哪", "怎")):
                continue
            for neuron_id in fiber.neuron_ids:
                neuron = neurons.get(neuron_id)
                if neuron is None or neuron.state != "active" or neuron.kind != "entity":
                    continue
                if neuron.content != name or neuron.id in seen:
                    continue
                seen.add(neuron.id)
                chosen.append((neuron.id, ANCHOR_CAP["entity"]))
    return chosen


def select_anchors(
    neurons: list[Neuron],
    query: str,
    workflow_ids: set[str],
) -> list[tuple[str, float]]:
    chosen: dict[str, float] = {}
    for neuron in neurons:
        if neuron.state != "active":
            continue
        cap = anchor_cap(neuron, workflow_ids)
        if len(neuron.content) >= SHORT_TEXT and neuron.content in query:
            chosen[neuron.id] = max(chosen.get(neuron.id, 0.0), cap)
            continue
        score = jaccard(neuron.content, query)
        if score >= ANCHOR_JACCARD:
            chosen[neuron.id] = max(chosen.get(neuron.id, 0.0), cap * score)
    ordered = sorted(chosen.items(), key=lambda item: item[1], reverse=True)
    return ordered


def query_dates(query: str) -> list[datetime]:
    found: list[datetime] = []
    for match in _DATE.findall(query):
        found.append(load_time(f"{match}T00:00:00Z"))
    return found


def time_window(moment: datetime, days: int) -> tuple[datetime, datetime]:
    return moment - timedelta(days=days), moment + timedelta(days=days)


def overlaps(fiber: Fiber, start: datetime, end: datetime) -> bool:
    if not fiber.time_start or not fiber.time_end:
        return False
    return load_time(fiber.time_start) <= end and load_time(fiber.time_end) >= start
