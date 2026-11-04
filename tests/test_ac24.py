"""AC-24: recover inside the grace window, prune after it, and refuse a pinned forget."""

from pathlib import Path

from dylan.memory.lifecycle import recover, soft_delete
from dylan.memory.prune import prune
from dylan.memory.recall import recall
from dylan.memory.store import MemoryStore


def test_recover_inside_grace_and_prune_after_it(bare_store, clock, make_fiber) -> None:
    first = make_fiber(bare_store, "甲组事实", summary="甲组事实", body="甲组事实")
    second = make_fiber(bare_store, "乙组事实", summary="乙组事实", body="乙组事实")
    soft_delete(bare_store, first)
    soft_delete(bare_store, second)
    clock.advance(days=3)
    restored, reason = recover(bare_store, bare_store.fiber(first.id))  # type: ignore[arg-type]
    assert reason == ""
    assert restored is not None
    assert restored.state == "active"
    assert restored.deleted_at is None
    clock.advance(days=6)
    blocked, reason = recover(bare_store, bare_store.fiber(second.id))  # type: ignore[arg-type]
    assert blocked is None
    assert reason == "宽限已过"
    prune(bare_store)
    assert bare_store.fiber(first.id).state == "active"  # type: ignore[union-attr]
    assert bare_store.fiber(second.id) is None
    result = recall(bare_store, "甲组事实", depth=1, max_hops=2, window_days=7, persist=False)
    assert first.id in [hit.fiber.id for hit in result.hits]


def test_forget_phrase_and_pinned_identity(tmp_path: Path, clock, invoke, make_fiber) -> None:
    from dylan.memory.encode import bootstrap
    from support.identity import TEXT

    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    banana = make_fiber(store, "香蕉很好吃", summary="香蕉很好吃", body="香蕉很好吃")
    store.close()
    _code, _out, err, _model = invoke(db, ["忘掉香蕉"])
    store = MemoryStore.open(db, clock)
    try:
        assert store.fiber(banana.id).state == "soft_deleted"  # type: ignore[union-attr]
    finally:
        store.close()
    _code, _out, err, _model = invoke(db, ["忘掉dylan"])
    assert "这条是钉住的，没有忘掉" in err
    store = MemoryStore.open(db, clock)
    try:
        identity = next(fiber for fiber in store.fibers() if fiber.memory_type == "identity")
        assert identity.state == "active"
        assert identity.pinned
    finally:
        store.close()
