"""Fake HTTP transport. It checks the model and the disabled thinking switch."""

from __future__ import annotations

from collections.abc import Iterator


class RecordingTransport:
    def __init__(self, expected_model: str = "deepseek-flash") -> None:
        self.expected_model = expected_model
        self.payloads: list[dict[str, object]] = []
        self.partial: str | None = None
        self.fail: Exception | None = None
        self.response = "好"
        self.json_response = '{"items":[]}'

    def stream(self, payload: dict[str, object]) -> Iterator[str]:
        self._check(payload)
        self.payloads.append(payload)
        if self.partial is not None:
            yield self.partial
        if self.fail is not None:
            raise self.fail
        yield self.response

    def complete(self, payload: dict[str, object]) -> str:
        self._check(payload)
        self.payloads.append(payload)
        if self.fail is not None:
            raise self.fail
        return self.json_response

    def _check(self, payload: dict[str, object]) -> None:
        assert payload["model"] == self.expected_model
        extra = payload["extra_body"]
        assert isinstance(extra, dict)
        thinking = extra["thinking"]
        assert isinstance(thinking, dict)
        assert thinking["type"] == "disabled"
        assert "max_tokens" not in payload
