"""AC-22: mature promotes a settled working fiber. A dry run leaves it working."""

from dylan.memory.consolidate.runner import run_strategies


def test_mature_promotes_and_dry_run_rolls_back(bare_store, make_fiber) -> None:
    fiber = make_fiber(
        bare_store,
        "甲组习惯",
        stage="working",
        frequency=5,
        conductivity=1.0,
        created_at="2026-10-26T00:00:00Z",
    )
    run_strategies(bare_store, ["mature"], dry_run=True)
    assert bare_store.fiber(fiber.id).stage == "working"  # type: ignore[union-attr]
    changed = run_strategies(bare_store, ["mature"])
    assert changed == [("mature", 1)]
    assert bare_store.fiber(fiber.id).stage == "semantic"  # type: ignore[union-attr]
