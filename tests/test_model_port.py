"""The DeepSeek client: request bodies, error categories, and the ports it must not touch."""

from __future__ import annotations

from pathlib import Path

from dylan.config import Settings
from dylan.errors import AuthFailed, ServiceError, TimeoutError_
from dylan.llm.client import DeepSeekClient, build_payload, map_error
from dylan.memory.constants import DEFAULT_BASE_URL, PRIVACY_NOTICE
from support.transport import RecordingTransport

_BANNED = (
    "NSPasteboard",
    "UIPasteboard",
    "pyperclip",
    "clipboard",
    "ImageGrab",
    "CGWindow",
    "CGDisplay",
    "screencapture",
    "NSWorkspace",
    "AppKit",
    "Quartz",
)


def test_stream_and_json_use_the_model_without_thinking() -> None:
    transport = RecordingTransport()
    client = DeepSeekClient(Settings(deepseek_api_key="test-key"), transport)
    assert list(client.stream_reply([{"role": "user", "content": "你好"}])) == ["好"]
    assert client.complete_json([{"role": "user", "content": "你好"}]) == {"items": []}
    assert len(transport.payloads) == 2
    assert transport.payloads[1]["response_format"] == {"type": "json_object"}


def test_custom_model_is_sent_with_thinking_disabled() -> None:
    payload = build_payload(
        Settings(deepseek_api_key="test-key", deepseek_model="other"), [], stream=True
    )
    assert payload["model"] == "other"
    assert payload["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "max_tokens" not in payload


def test_errors_keep_only_their_category() -> None:
    class ReadTimeout(Exception):
        def __str__(self) -> str:
            return "sk-abcdefghijklmnopqrst"

    class AuthenticationError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    mapped = map_error(ReadTimeout())
    assert isinstance(mapped, TimeoutError_) and "sk-" not in str(mapped)
    assert isinstance(map_error(AuthenticationError()), AuthFailed)
    assert isinstance(map_error(RateLimitError()), ServiceError)
    assert map_error(ConnectionError("down")).category == "网络中断"
    assert Settings().dylan_timeout_seconds == 60


def test_interrupted_reply_is_shown_and_not_stored(tmp_path: Path, clock, invoke) -> None:
    from dylan.errors import NetworkError
    from dylan.llm.fake import FakeModel
    from dylan.memory.store import MemoryStore

    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.partial = "ZZPARTIAL"
    model.fail = NetworkError()
    code, out, err, model = invoke(db, ["请记住甲组的暗号", "exit"], model=model)
    assert code == 0
    assert "ZZPARTIAL" in out and "网络中断" in err
    assert not model.calls("note")
    store = MemoryStore.open(db, clock)
    try:
        assert not store.search_text("ZZPARTIAL")
        assert not store.search_text("请记住甲组的暗号")
    finally:
        store.close()


def test_no_desktop_capture_and_the_llm_never_opens_the_store() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "dylan"
    for path in source.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in _BANNED:
            assert name not in text, f"{path} contains {name}"
    for path in (source / "llm").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "dylan.memory.store" not in text and "sqlite3" not in text
    assert PRIVACY_NOTICE == "对话内容和被唤起的记忆会发送给 DeepSeek。"
    assert DEFAULT_BASE_URL == "https://api.deepseek.com"
