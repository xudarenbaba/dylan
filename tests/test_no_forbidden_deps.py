"""Forbidden packages, an empty example key, and the Python 3.12 declaration."""

from __future__ import annotations

import re
from pathlib import Path

_PACKAGES = (
    "neural-memory",
    "chromadb",
    "faiss-cpu",
    "faiss-gpu",
    "qdrant-client",
    "pymilvus",
    "lancedb",
    "pgvector",
    "sentence-transformers",
    "FlagEmbedding",
    "numpy",
    "scipy",
    "networkx",
    "torch",
    "jieba",
    "pkuseg",
    "spacy",
    "fastapi",
    "flask",
    "uvicorn",
    "gradio",
    "streamlit",
    "PySide6",
    "PyQt6",
    "textual",
    "rich",
)

_IGNORE = (".env", "data/", "__pycache__/", ".pytest_cache/", ".ruff_cache/", "*.db")


def test_forbidden_packages_and_import_direction() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [root / "src" / "dylan"]
    targets.extend(
        root / name for name in ("requirements.txt", "requirements-dev.txt", "environment.yml")
    )
    pattern = "|".join(re.escape(name) for name in _PACKAGES)
    banned = re.compile(rf"(?<![A-Za-z0-9_])(?:{pattern})(?![A-Za-z0-9_])")
    for target in targets:
        paths = target.rglob("*.py") if target.is_dir() else [target]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            match = banned.search(text)
            assert match is None, f"{path} contains {match.group(0) if match else ''}"
    for path in (root / "src" / "dylan" / "memory").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "openai" not in text
        assert "dylan.dialogue" not in text
        assert "dylan.cli" not in text
    for path in (root / "src" / "dylan" / "dialogue").rglob("*.py"):
        assert "sqlite3" not in path.read_text(encoding="utf-8")
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY=\n" in example or example.startswith("DEEPSEEK_API_KEY=\n")
    assert "DEEPSEEK_API_KEY=sk-" not in example
    ignore = (root / ".gitignore").read_text(encoding="utf-8")
    for name in _IGNORE:
        assert name in ignore
    assert "*.db-wal" in ignore
    assert "*.db-shm" in ignore
    yml = (root / "environment.yml").read_text(encoding="utf-8")
    assert "python=3.12" in yml
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.12"' in project
