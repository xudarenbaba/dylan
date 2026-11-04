"""Runtime limits. Defaults live in constants; configuration may replace them."""

from __future__ import annotations

from dataclasses import dataclass

from dylan.memory.constants import (
    ACTIVATION_THRESHOLD,
    BUFFER_TURNS,
    DECAY_RATE,
    DEDUP_JACCARD,
    HOT_CHARS,
    MERGE_JACCARD,
    PRUNE_INACTIVE_DAYS,
    PRUNE_WEIGHT,
    RECALL_CHARS,
    RECALL_LIMIT,
    SOFT_DELETE_GRACE_DAYS,
    TAG_JACCARD,
)


@dataclass(frozen=True)
class Limits:
    activation_threshold: float = ACTIVATION_THRESHOLD
    decay_rate: float = DECAY_RATE
    prune_weight: float = PRUNE_WEIGHT
    prune_inactive_days: float = PRUNE_INACTIVE_DAYS
    grace_days: float = SOFT_DELETE_GRACE_DAYS
    dedup_jaccard: float = DEDUP_JACCARD
    merge_jaccard: float = MERGE_JACCARD
    tag_jaccard: float = TAG_JACCARD
    recall_limit: int = RECALL_LIMIT
    recall_chars: int = RECALL_CHARS
    hot_chars: int = HOT_CHARS
    buffer_turns: int = BUFFER_TURNS
    auto_dream: bool = False
