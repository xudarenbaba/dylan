"""AC-29: health suggests mature, and a short exit runs the suggested habit."""

from pathlib import Path

from dylan.memory.consolidate.runner import short_consolidation
from dylan.memory.encode import bootstrap
from dylan.memory.store import MemoryStore
from support.identity import TEXT


def test_health_suggests_mature(tmp_path: Path, clock, invoke, make_fiber) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    make_fiber(
        store,
        "甲组成熟",
        stage="working",
        frequency=5,
        conductivity=1.0,
        created_at="2026-10-26T00:00:00Z",
    )
    store.close()
    code, out, err, _model = invoke(db, argv=["health"], key="")
    assert code == 0, err
    for label in ("成熟比例", "连通", "新鲜", "冲突", "建议"):
        assert f"{label}:" in out
    assert "建议: mature" in out


def test_short_consolidation_follows_learn_habits(store) -> None:
    left = store.ensure_neuron("concept", "甲点")
    right = store.ensure_neuron("concept", "乙点")
    signature = f"{left.id}>{right.id}"
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        store.observe_sequence(signature, day)
    done = short_consolidation(store)
    assert [name for name, _count in done] == ["dedup", "prune", "mature", "learn_habits"]
