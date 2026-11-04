"""AC-20: depth 3 walks 结果 —caused_by→ 原因 even though the question never says 原因."""

from dylan.memory.recall import recall
from support.graph import build_graph


def test_cause_appears_on_the_activation_path(bare_store) -> None:
    ids = build_graph(
        bare_store,
        [("结果", "entity"), ("原因", "entity")],
        [("结果", "原因", "caused_by", 1.0)],
        [["结果", "原因"]],
    )
    query = "为什么这个结果"
    assert "原因" not in query
    result = recall(bare_store, query, depth=3, max_hops=6, window_days=365, persist=False)
    paths = [hit.path for hit in result.hits]
    assert any(ids["原因"] in path and "caused_by" in path for path in paths)
