"""AC-28: three distinct days become one workflow. Two turns in one session do not."""

from pathlib import Path

from dylan.memory.consolidate import habits
from dylan.memory.store import MemoryStore


def test_three_dates_become_a_workflow(bare_store) -> None:
    left = bare_store.ensure_neuron("concept", "甲点")
    right = bare_store.ensure_neuron("concept", "乙点")
    signature = f"{left.id}>{right.id}"
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        bare_store.observe_sequence(signature, day)
    assert habits.run(bare_store) == 1
    workflows = [fiber for fiber in bare_store.fibers() if fiber.memory_type == "workflow"]
    assert len(workflows) == 1
    assert any(
        synapse.type == "before" and synapse.source_id == left.id and synapse.target_id == right.id
        for synapse in bare_store.synapses()
    )


def test_two_turns_do_not_create_a_workflow(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["甲点然后乙点", "甲点然后乙点"])
    store = MemoryStore.open(db, clock)
    try:
        assert not any(fiber.memory_type == "workflow" for fiber in store.fibers())
        assert any(synapse.type == "before" for synapse in store.synapses())
    finally:
        store.close()
