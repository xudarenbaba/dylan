"""DeepSeek chat client. Thinking mode is explicitly disabled. No max_tokens."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from dylan.config import Settings
from dylan.errors import AuthFailed, DylanError, NetworkError, ServiceError, TimeoutError_


class ModelPort(Protocol):
    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]: ...

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]: ...


class Transport(Protocol):
    def stream(self, payload: dict[str, object]) -> Iterator[str]: ...

    def complete(self, payload: dict[str, object]) -> str: ...


def build_payload(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    stream: bool,
    json_mode: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": settings.deepseek_model,
        "stream": stream,
        "messages": messages,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def map_error(exc: Exception) -> DylanError:
    if isinstance(exc, DylanError):
        return exc
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return TimeoutError_()
    if "auth" in name or "permission" in name:
        return AuthFailed()
    if "status" in name or "ratelimit" in name:
        return ServiceError()
    return NetworkError()


class OpenAITransport:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: object | None = None

    def _sdk(self) -> object:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.dylan_timeout_seconds,
            )
        return self._client

    def stream(self, payload: dict[str, object]) -> Iterator[str]:
        client = self._sdk()
        response = client.chat.completions.create(  # type: ignore[attr-defined]
            model=payload["model"],
            messages=payload["messages"],
            stream=True,
            extra_body=payload["extra_body"],
        )
        for chunk in response:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            text = getattr(delta, "content", None) if delta is not None else None
            if text:
                yield text

    def complete(self, payload: dict[str, object]) -> str:
        client = self._sdk()
        kwargs: dict[str, object] = {
            "model": payload["model"],
            "messages": payload["messages"],
            "stream": False,
            "extra_body": payload["extra_body"],
        }
        if "response_format" in payload:
            kwargs["response_format"] = payload["response_format"]
        response = client.chat.completions.create(**kwargs)  # type: ignore[attr-defined]
        return response.choices[0].message.content or ""


class DeepSeekClient:
    def __init__(self, settings: Settings, transport: Transport | None = None) -> None:
        self.settings = settings
        self.transport = transport or OpenAITransport(settings)

    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]:
        payload = build_payload(self.settings, messages, stream=True)
        try:
            yield from self.transport.stream(payload)
        except DylanError:
            raise
        except Exception as exc:
            raise map_error(exc) from None

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        payload = build_payload(self.settings, messages, stream=False, json_mode=True)
        try:
            raw = self.transport.complete(payload)
        except DylanError:
            raise
        except Exception as exc:
            raise map_error(exc) from None
        import json

        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NetworkError() from exc
        if not isinstance(loaded, dict):
            raise NetworkError()
        return loaded
