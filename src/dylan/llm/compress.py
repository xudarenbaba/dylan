"""Optional model compression. Failure leaves the fiber tier unchanged."""

from __future__ import annotations

import json

from dylan.llm.client import ModelPort


class ModelCompressor:
    def __init__(self, model: ModelPort) -> None:
        self.model = model

    def summaries(self, text: str) -> tuple[str, str, str] | None:
        messages = [
            {
                "role": "system",
                "content": '只输出 JSON：{"summary":"","essence":"","ghost":""}',
            },
            {"role": "user", "content": text},
        ]
        try:
            payload = self.model.complete_json(messages)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        summary = str(payload.get("summary") or "")
        essence = str(payload.get("essence") or "")
        ghost = str(payload.get("ghost") or "")
        if not any((summary, essence, ghost)):
            return None
        return summary, essence, ghost


def dumps_disabled(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)
