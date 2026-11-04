"""Identity prose shared by tests that open their own database."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "persona" / "identity.md"
TEXT = PATH.read_text(encoding="utf-8")
