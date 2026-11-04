"""AC-26: a pinned fiber ignores decay and prune."""

from dylan.memory.decay import apply_decay
from dylan.memory.lifecycle import pin
from dylan.memory.prune import prune


def test_pinned_fiber_keeps_its_conductivity(bare_store, clock, make_fiber) -> None:
    fiber = make_fiber(bare_store, "甲组备忘", summary="甲组备忘")
    pinned = pin(bare_store, fiber)
    before = pinned.conductivity
    clock.advance(days=180)
    apply_decay(bare_store)
    prune(bare_store)
    kept = bare_store.fiber(fiber.id)
    assert kept is not None
    assert kept.conductivity == before
    assert kept.pinned
    assert kept.state == "active"
