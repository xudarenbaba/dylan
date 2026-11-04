"""AC-07: activation spreads 项目 → dylan → DeepSeek without an embedding index."""

from dylan.memory.recall import recall
from support.graph import build_graph


def test_downstream_fiber_is_reached_from_the_project_anchor(bare_store) -> None:
    ids = build_graph(
        bare_store,
        [("项目", "entity"), ("dylan", "entity"), ("DeepSeek", "entity")],
        [
            ("项目", "dylan", "involves", 1.0),
            ("dylan", "DeepSeek", "related_to", 1.0),
        ],
        [["项目", "dylan"], ["dylan", "DeepSeek"]],
    )
    result = recall(
        bare_store,
        "这个项目的模型是哪家",
        depth=1,
        max_hops=2,
        window_days=7,
        persist=False,
    )
    assert "DeepSeek" not in "这个项目的模型是哪家"
    assert any(ids["DeepSeek"] in hit.path for hit in result.hits)
    assert any(ids["DeepSeek"] in hit.fiber.neuron_ids for hit in result.hits)
