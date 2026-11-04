"""AC-27: a frozen fiber drops out of recall and does not decay until it thaws."""

from dylan.memory.decay import apply_decay
from dylan.memory.lifecycle import freeze, thaw
from dylan.memory.recall import recall


def test_freeze_hides_recall_and_thaw_restores_it(bare_store, clock, make_fiber) -> None:
    fiber = make_fiber(bare_store, "甲组地点", kind="entity", summary="甲组地点", body="甲组地点")
    found = recall(bare_store, "甲组地点", depth=1, max_hops=2, window_days=7, persist=False)
    assert fiber.id in [hit.fiber.id for hit in found.hits]
    freeze(bare_store, bare_store.fiber(fiber.id))  # type: ignore[arg-type]
    hidden = recall(bare_store, "甲组地点", depth=1, max_hops=2, window_days=7, persist=False)
    assert fiber.id not in [hit.fiber.id for hit in hidden.hits]
    before = bare_store.fiber(fiber.id).conductivity  # type: ignore[union-attr]
    clock.advance(days=30)
    apply_decay(bare_store)
    assert bare_store.fiber(fiber.id).conductivity == before  # type: ignore[union-attr]
    thaw(bare_store, bare_store.fiber(fiber.id))  # type: ignore[arg-type]
    restored = recall(bare_store, "甲组地点", depth=1, max_hops=2, window_days=7, persist=False)
    assert fiber.id in [hit.fiber.id for hit in restored.hits]
