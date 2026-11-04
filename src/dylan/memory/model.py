"""Validated memory records."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    source: str
    confidence: str
    trust: float


class Neuron(BaseModel):
    id: str
    kind: str
    content: str
    content_key: str
    pinned: bool = False
    state: str = "active"
    created_at: str
    deleted_at: str | None = None


class Synapse(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: str
    direction: str
    base_weight: float
    weight: float
    rehearsal_count: int = 0
    last_activated_at: str | None = None
    decay_cursor: str
    created_at: str


class Fiber(BaseModel):
    id: str
    anchor_neuron_id: str
    neuron_ids: list[str]
    synapse_ids: list[str] = Field(default_factory=list)
    conductivity: float
    base_conductivity: float
    coherence: float = 1.0
    salience: float = 0.5
    frequency: int = 1
    summary: str
    essence: str = ""
    ghost: str = ""
    body: str | None = None
    compression_tier: int = 0
    stage: str = "episodic"
    memory_type: str
    priority: int = 5
    tier: str = "warm"
    state: str = "active"
    pinned: bool = False
    time_start: str | None = None
    time_end: str | None = None
    expires_at: str | None = None
    rehearsal_count: int = 0
    last_conducted_at: str | None = None
    last_activated_at: str | None = None
    created_at: str
    decay_cursor: str
    deleted_at: str | None = None
    provenance: Provenance
    recall_dates: list[str] = Field(default_factory=list)
    confidence_value: float | None = None
    tags: list[str] = Field(default_factory=list)
    auto_session: bool = False
