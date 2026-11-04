"""Temporary brains, a fixed clock, and a chat entry that never reads a real .env."""

from __future__ import annotations

import os
import sys
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest

from dylan.clock import dump_time
from dylan.config import Settings
from dylan.llm.fake import FakeModel
from dylan.memory.encode import bootstrap
from dylan.memory.model import Fiber, Provenance
from dylan.memory.store import MemoryStore, day_key

_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))

ROOT = _TESTS.parent
IDENTITY_PATH = ROOT / "persona" / "identity.md"
IDENTITY = IDENTITY_PATH.read_text(encoding="utf-8")


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
    bootstrap(bare_store, IDENTITY)
    return bare_store


@pytest.fixture
def make_fiber():
    return _make_fiber


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
    show_thought: bool = False,
    stdin: object | None = None,
    settings_extra: dict[str, object] | None = None,
) -> tuple[int, str, str, FakeModel]:
    from dylan.cli.main import main

    chosen = model if model is not None else FakeModel()
    payload: dict[str, object] = {
        "deepseek_api_key": key,
        "dylan_db": str(db),
        "dylan_show_thought": show_thought,
    }
    if settings_extra:
        payload.update(settings_extra)
    out, err = StringIO(), StringIO()
    if stdin is None:
        text = "" if not lines else "\n".join(lines) + "\n"
        stdin = StringIO(text)
    code = main(
        ["chat"] if argv is None else argv,
        clock=clock,  # type: ignore[arg-type]
        model=chosen,
        stdin=stdin,
        stdout=out,
        stderr=err,
        settings=Settings(**payload),  # type: ignore[arg-type]
        env_file=None,
        identity_path=identity_path,
    )
    return code, out.getvalue(), err.getvalue(), chosen


def _make_fiber(store: MemoryStore, content: str, **overrides: object) -> Fiber:
    kind = str(overrides.pop("kind", "concept"))
    neuron_ids = overrides.pop("neuron_ids", None)
    if neuron_ids is None:
        neuron_ids = [store.ensure_neuron(kind, content).id]
    ids = list(neuron_ids)  # type: ignore[arg-type]
    now = dump_time(store.clock.now())
    conductivity = float(overrides.pop("conductivity", 1.0))  # type: ignore[arg-type]
    fiber = Fiber(
        id=str(uuid4()),
        anchor_neuron_id=ids[0],
        neuron_ids=ids,
        synapse_ids=list(overrides.pop("synapse_ids", [])),  # type: ignore[arg-type]
        conductivity=conductivity,
        base_conductivity=float(overrides.pop("base_conductivity", conductivity)),  # type: ignore[arg-type]
        summary=str(overrides.pop("summary", content)),
        essence=str(overrides.pop("essence", content)),
        ghost=str(overrides.pop("ghost", content[:40])),
        body=overrides.pop("body", content),  # type: ignore[arg-type]
        compression_tier=int(overrides.pop("compression_tier", 0)),  # type: ignore[arg-type]
        stage=str(overrides.pop("stage", "episodic")),
        memory_type=str(overrides.pop("memory_type", "fact")),
        priority=int(overrides.pop("priority", 5)),  # type: ignore[arg-type]
        tier=str(overrides.pop("tier", "warm")),
        state=str(overrides.pop("state", "active")),
        pinned=bool(overrides.pop("pinned", False)),
        time_start=overrides.pop("time_start", None),  # type: ignore[arg-type]
        time_end=overrides.pop("time_end", None),  # type: ignore[arg-type]
        expires_at=overrides.pop("expires_at", None),  # type: ignore[arg-type]
        rehearsal_count=int(overrides.pop("rehearsal_count", 0)),  # type: ignore[arg-type]
        frequency=int(overrides.pop("frequency", 1)),  # type: ignore[arg-type]
        last_conducted_at=str(overrides.pop("last_conducted_at", now)),
        last_activated_at=str(overrides.pop("last_activated_at", now)),
        created_at=str(overrides.pop("created_at", now)),
        decay_cursor=str(overrides.pop("decay_cursor", now)),
        deleted_at=overrides.pop("deleted_at", None),  # type: ignore[arg-type]
        provenance=overrides.pop(  # type: ignore[arg-type]
            "provenance",
            Provenance(source="user_input", confidence="high", trust=0.9),
        ),
        recall_dates=list(overrides.pop("recall_dates", [day_key(now)])),  # type: ignore[arg-type]
        confidence_value=overrides.pop("confidence_value", None),  # type: ignore[arg-type]
        tags=list(overrides.pop("tags", [])),  # type: ignore[arg-type]
        auto_session=bool(overrides.pop("auto_session", False)),
    )
    if overrides:
        unknown = ", ".join(sorted(overrides))
        raise TypeError(f"unknown fiber fields: {unknown}")
    store.insert_fiber(fiber)
    return fiber
