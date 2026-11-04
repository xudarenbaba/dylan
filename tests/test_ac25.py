"""AC-25: dream memories stay inferred, and one run creates at most three bridges."""

from dylan.memory.consolidate import dream
from dylan.memory.recall import recall


def test_dream_fiber_is_never_clear(bare_store) -> None:
    left = bare_store.ensure_neuron("concept", "甲点")
    right = bare_store.ensure_neuron("concept", "乙点")
    for _ in range(2):
        bare_store.add_recall_run([left.id])
        bare_store.add_recall_run([right.id])
    assert dream.run(bare_store) == 1
    fiber = next(item for item in bare_store.fibers() if item.provenance.source == "dream")
    assert fiber.provenance.confidence == "inferred"
    assert fiber.memory_type == "insight"
    result = recall(bare_store, "甲点与乙点", depth=1, max_hops=2, window_days=7, persist=False)
    assert fiber.id in [hit.fiber.id for hit in result.hits]
    assert result.certainty != "clear"
    assert all(hit.certainty != "clear" for hit in result.hits)


def test_dream_keeps_only_the_three_strongest_pairs(bare_store) -> None:
    names = ["甲一", "甲二", "乙一", "乙二", "丙一", "丙二", "丁一", "丁二"]
    neurons = {name: bare_store.ensure_neuron("concept", name) for name in names}
    counts = {"甲": 5, "乙": 4, "丙": 3, "丁": 2}
    for label, count in counts.items():
        for _ in range(count):
            bare_store.add_recall_run([neurons[f"{label}一"].id])
            bare_store.add_recall_run([neurons[f"{label}二"].id])
    assert dream.run(bare_store) == 3
    dreamed = [fiber for fiber in bare_store.fibers() if fiber.provenance.source == "dream"]
    assert len(dreamed) == 3
    text = " ".join(fiber.summary for fiber in dreamed)
    assert "丁一" not in text
    assert "丁二" not in text
