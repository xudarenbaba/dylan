"""Environment configuration. The key is read only from DEEPSEEK_API_KEY."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from dylan.memory.constants import (
    AWARENESS_CHARS,
    BUFFER_TURNS,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEZONE,
    RECALL_CHARS,
    RECALL_LIMIT,
    TIMEOUT_SECONDS,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    deepseek_api_key: str = ""
    deepseek_model: str = DEFAULT_MODEL
    deepseek_base_url: str = DEFAULT_BASE_URL
    dylan_db: str = "data/dylan.db"
    dylan_timezone: str = DEFAULT_TIMEZONE
    dylan_timeout_seconds: int = TIMEOUT_SECONDS
    dylan_buffer_turns: int = BUFFER_TURNS
    dylan_recall_limit: int = RECALL_LIMIT
    dylan_recall_chars: int = RECALL_CHARS
    dylan_awareness_chars: int = AWARENESS_CHARS
    dylan_show_mind: bool = False
