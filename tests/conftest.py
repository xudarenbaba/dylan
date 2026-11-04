"""Temporary brains, a fixed clock, a scripted model, and a chat entry that never reads .env."""

from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path

import pytest

from dylan.clock import zone
from dylan.config import Settings
from dylan.llm.fake import FakeModel
from dylan.memory.life import Handles, birth
from dylan.memory.ops import Context, Writer
from dylan.memory.store import MemoryStore

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

ROOT = _TESTS.parent
LETTER_PATH = ROOT / "persona" / "identity.md"
LETTER = LETTER_PATH.read_text(encoding="utf-8")
TZ = zone("Asia/Shanghai")


@pytest.fixture(autouse=True)
def _strip_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("DEEPSEEK_") or key.startswith("DYLAN_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def clock():
    from support.clock import fixed_clock

    return fixed_clock()


@pytest.fixture
def bare_store(tmp_path: Path, clock):
    store = MemoryStore.create(tmp_path / "dylan.db", clock)
    yield store
    store.close()


@pytest.fixture
def store(bare_store):
    """A brain that has been born from the real letter."""
    birth(bare_store, LETTER, FakeModel().default_birth(LETTER), TZ)
    return bare_store


@pytest.fixture
def note(store):
    """Apply one scripted note as if she had just heard user_text and replied reply_text."""

    def _note(
        ops: list[dict],
        *,
        user_text: str = "",
        reply_text: str = "",
        shown: list | None = None,
        phase: str = "note",
        api_key: str = "",
    ):
        handles = Handles()
        for fiber in shown or []:
            handles.add(fiber)
        ctx = Context(
            phase=phase,
            tz=TZ,
            api_key=api_key,
            user_text=user_text,
            reply_text=reply_text,
            handles=dict(handles.by_handle),
        )
        with store.transaction():
            return Writer(store, ctx).apply(ops)

    return _note


@pytest.fixture
def invoke(clock):
    def _invoke(db: Path, lines: list[str] | None = None, **kwargs):
        return run_main(db, clock, lines, **kwargs)

    return _invoke


def run_main(
    db: Path,
    clock: object,
    lines: list[str] | None = None,
    *,
    argv: list[str] | None = None,
    key: str = "test-key",
    model: FakeModel | None = None,
    identity_path: Path | None = None,
    show_mind: bool = False,
    stdin: object | None = None,
) -> tuple[int, str, str, FakeModel]:
    from dylan.cli.main import main

    chosen = model if model is not None else FakeModel()
    out, err = StringIO(), StringIO()
    if stdin is None:
        stdin = StringIO("" if not lines else "\n".join(lines) + "\n")
    code = main(
        ["chat"] if argv is None else argv,
        clock=clock,  # type: ignore[arg-type]
        model=chosen,
        stdin=stdin,
        stdout=out,
        stderr=err,
        settings=Settings(
            deepseek_api_key=key, dylan_db=str(db), dylan_show_mind=show_mind
        ),
        env_file=None,
        identity_path=identity_path,
    )
    return code, out.getvalue(), err.getvalue(), chosen


def fact(statement: str, evidence: str, **extra: object) -> dict:
    """A scripted add op for something he said."""
    op: dict[str, object] = {
        "op": "add",
        "type": "fact",
        "about": "赵旭",
        "statement": statement,
        "evidence": evidence,
        "source": "user",
    }
    op.update(extra)
    return op
