"""Validated memory records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Neuron(BaseModel):
    id: str
    kind: str
    name: str
    name_key: str
    innate: bool = False
    created_at: str


class Synapse(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: str
    label: str = ""
    base_weight: float
    rehearsal_count: int = 0
    innate: bool = False
    created_at: str
    last_activated_at: str


class Emotion(BaseModel):
    who: str
    label: str
    intensity: float


class Mood(BaseModel):
    label: str
    intensity: float
    cause: str = ""
    at: str


class Fiber(BaseModel):
    id: str
    anchor_id: str
    memory_type: str
    about: str
    statement: str = ""
    detail: str = ""
    gist: str = ""
    evidence: str = ""
    source: str
    importance: int
    emotion: Emotion | None = None
    confidence: float | None = None
    strength: float
    stage: str = "fresh"
    detail_level: int = 0
    state: str = "active"
    occurred_start: str | None = None
    occurred_end: str | None = None
    due_at: str | None = None
    trigger: str = ""
    valid_until: str | None = None
    session_id: str | None = None
    created_at: str
    updated_at: str
    state_changed_at: str
    last_recalled_at: str | None = None
    recall_count: int = 0
    recall_days: list[str] = Field(default_factory=list)
    settled_at: str
    neuron_ids: list[str] = Field(default_factory=list)
    synapse_ids: list[str] = Field(default_factory=list)
    cues: list[str] = Field(default_factory=list)


class Turn(BaseModel):
    id: str
    session_id: str
    position: int
    at: str
    user_text: str
    reply_text: str
    noted: bool = False
    attempts: int = 0


class Session(BaseModel):
    id: str
    started_at: str
    ended_at: str | None = None
    summary: str = ""
    slept: bool = False
