"""Environment configuration. The key is read only from DEEPSEEK_API_KEY."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from dylan.memory.constants import (
    ACTIVATION_THRESHOLD,
    BUFFER_TURNS,
    DECAY_RATE,
    DEDUP_JACCARD,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    HOT_CHARS,
    MERGE_JACCARD,
    PRUNE_INACTIVE_DAYS,
    PRUNE_WEIGHT,
    RECALL_CHARS,
    RECALL_LIMIT,
    SOFT_DELETE_GRACE_DAYS,
    TIMEOUT_SECONDS,
)
from dylan.memory.limits import Limits


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = DEFAULT_MODEL
    deepseek_base_url: str = DEFAULT_BASE_URL
    dylan_db: str = "data/dylan.db"
    dylan_timeout_seconds: int = TIMEOUT_SECONDS
    dylan_buffer_turns: int = BUFFER_TURNS
    dylan_recall_limit: int = RECALL_LIMIT
    dylan_recall_chars: int = RECALL_CHARS
    dylan_hot_chars: int = HOT_CHARS
    dylan_activation_threshold: float = ACTIVATION_THRESHOLD
    dylan_decay_rate: float = DECAY_RATE
    dylan_prune_weight: float = PRUNE_WEIGHT
    dylan_prune_inactive_days: float = PRUNE_INACTIVE_DAYS
    dylan_soft_delete_grace_days: float = SOFT_DELETE_GRACE_DAYS
    dylan_dedup_jaccard: float = DEDUP_JACCARD
    dylan_merge_jaccard: float = MERGE_JACCARD
    dylan_auto_dream: bool = False
    dylan_show_thought: bool = False
    dylan_compress_with_model: bool = False

    def limits(self) -> Limits:
        return Limits(
            activation_threshold=self.dylan_activation_threshold,
            decay_rate=self.dylan_decay_rate,
            prune_weight=self.dylan_prune_weight,
            prune_inactive_days=self.dylan_prune_inactive_days,
            grace_days=self.dylan_soft_delete_grace_days,
            dedup_jaccard=self.dylan_dedup_jaccard,
            merge_jaccard=self.dylan_merge_jaccard,
            recall_limit=self.dylan_recall_limit,
            recall_chars=self.dylan_recall_chars,
            hot_chars=self.dylan_hot_chars,
            buffer_turns=self.dylan_buffer_turns,
            auto_dream=self.dylan_auto_dream,
        )
