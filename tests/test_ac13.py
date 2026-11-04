"""AC-13: captured bodies use deepseek-flash and disable thinking. No max_tokens."""

from dylan.config import Settings
from dylan.llm.client import DeepSeekClient, build_payload
from support.transport import RecordingTransport


def test_stream_and_json_disable_thinking() -> None:
    transport = RecordingTransport()
    client = DeepSeekClient(Settings(deepseek_api_key="test-key"), transport)
    assert list(client.stream_reply([{"role": "user", "content": "你好"}])) == ["好"]
    assert client.complete_json([{"role": "user", "content": "你好"}]) == {"items": []}
    assert len(transport.payloads) == 2
    for payload in transport.payloads:
        assert payload["model"] == "deepseek-flash"
        extra = payload["extra_body"]
        assert isinstance(extra, dict)
        thinking = extra["thinking"]
        assert isinstance(thinking, dict)
        assert thinking["type"] == "disabled"
        assert "max_tokens" not in payload
    assert transport.payloads[1]["response_format"] == {"type": "json_object"}


def test_custom_model_is_still_sent_with_thinking_disabled() -> None:
    payload = build_payload(
        Settings(deepseek_api_key="test-key", deepseek_model="other"),
        [],
        stream=True,
    )
    assert payload["model"] == "other"
    extra = payload["extra_body"]
    assert isinstance(extra, dict)
    thinking = extra["thinking"]
    assert isinstance(thinking, dict)
    assert thinking["type"] == "disabled"
    assert "max_tokens" not in payload
