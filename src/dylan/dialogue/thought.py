"""Internal thought record. The visible answer is not allowed to recite these field names."""

from __future__ import annotations

from pydantic import BaseModel, Field

from dylan.clock import days_between, load_time
from dylan.memory.compress import visible_text
from dylan.memory.recall import Recall


class RecalledItem(BaseModel):
    summary: str
    memory_type: str
    stage: str
    strength: float
    age: str
    compression_tier: int
    path: list[str]
    source: str
    certainty: str


class ConflictItem(BaseModel):
    left_id: str
    right_id: str
    left: str
    right: str


class Thought(BaseModel):
    depth: int
    recalled: list[RecalledItem] = Field(default_factory=list)
    certainty: str = "none"
    conflicts: list[ConflictItem] = Field(default_factory=list)
    novel: list[str] = Field(default_factory=list)
    reply_intent: str = "unknown"


def build_thought(recall: Recall, novel: list[str], *, now_text: str) -> Thought:
    items: list[RecalledItem] = []
    now = load_time(now_text)
    for hit in recall.hits:
        days = max(0.0, days_between(load_time(hit.fiber.created_at), now))
        items.append(
            RecalledItem(
                summary=visible_text(hit.fiber, now),
                memory_type=hit.fiber.memory_type,
                stage=hit.fiber.stage,
                strength=hit.score,
                age=f"{int(days)}天",
                compression_tier=hit.fiber.compression_tier,
                path=hit.path,
                source=hit.fiber.provenance.source,
                certainty=hit.certainty,
            )
        )
    conflicts = [ConflictItem.model_validate(item) for item in recall.conflicts]
    return Thought(
        depth=recall.depth,
        recalled=items,
        certainty=recall.certainty,
        conflicts=conflicts,
        novel=novel,
        reply_intent=recall.intent,
    )
