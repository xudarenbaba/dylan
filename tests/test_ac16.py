"""AC-16: two anchors raise the shared neuron and bind co_occurs. One anchor does not."""

from pathlib import Path

from dylan.memory.recall import recall
from dylan.memory.roles import direction_for
from dylan.memory.store import MemoryStore


def _wire(store: MemoryStore, names: list[str]) -> str:
    shared = store.ensure_neuron("entity", "颜色")
    anchors = [store.ensure_neuron("entity", name) for name in names]
    for anchor in anchors:
        store.add_synapse(
            anchor.id,
            shared.id,
            "related_to",
            direction=direction_for("related_to"),
            base_weight=1.0,
        )
    return shared.id


def test_joint_anchors_bonus_and_co_occurrence(tmp_path: Path, clock) -> None:
    single = MemoryStore.create(tmp_path / "single.db", clock)
    joint = MemoryStore.create(tmp_path / "joint.db", clock)
    try:
        color_one = _wire(single, ["红色"])
        alone = recall(single, "红色", depth=1, max_hops=2, window_days=7)
        color_two = _wire(joint, ["红色", "蓝色"])
        both = recall(joint, "红色蓝色", depth=1, max_hops=2, window_days=7)
        assert both.activation[color_two] > alone.activation[color_one]
        assert any(synapse.type == "co_occurs" for synapse in joint.synapses())
        assert not any(synapse.type == "co_occurs" for synapse in single.synapses())
    finally:
        single.close()
        joint.close()
