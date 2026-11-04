"""AC-14: the runtime path has no screen, clipboard, or foreground-window access."""

from pathlib import Path

from dylan.memory.constants import DEFAULT_BASE_URL, PRIVACY_NOTICE

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


def test_source_has_no_desktop_capture_and_llm_does_not_open_the_store() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "src" / "dylan"
    for path in source.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in _BANNED:
            assert name not in text, f"{path} contains {name}"
    for path in (source / "llm").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "dylan.memory.store" not in text
        assert "sqlite3" not in text
    assert PRIVACY_NOTICE == "对话内容和被唤起的记忆会发送给 DeepSeek。"
    assert DEFAULT_BASE_URL == "https://api.deepseek.com"
