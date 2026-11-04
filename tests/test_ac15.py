"""AC-15: equal synapse weight, higher fiber conductivity, higher downstream activation."""

from dylan.memory.recall import recall
from dylan.memory.roles import direction_for


def test_higher_conductivity_raises_downstream_activation(bare_store, make_fiber) -> None:
    origin = bare_store.ensure_neuron("entity", "甲点")
    high = bare_store.ensure_neuron("entity", "下游一")
    low = bare_store.ensure_neuron("entity", "下游二")
    strong = bare_store.add_synapse(
        origin.id,
        high.id,
        "related_to",
        direction=direction_for("related_to"),
        base_weight=1.0,
    )
    weak = bare_store.add_synapse(
        origin.id,
        low.id,
        "related_to",
        direction=direction_for("related_to"),
        base_weight=1.0,
    )
    make_fiber(
        bare_store,
        "通路甲",
        neuron_ids=[origin.id, high.id],
        synapse_ids=[strong.id],
        conductivity=1.0,
    )
    make_fiber(
        bare_store,
        "通路乙",
        neuron_ids=[origin.id, low.id],
        synapse_ids=[weak.id],
        conductivity=0.8,
    )
    result = recall(bare_store, "甲点", depth=1, max_hops=2, window_days=7, persist=False)
    assert result.activation[high.id] > result.activation[low.id]
