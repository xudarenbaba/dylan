"""AC-17: a dated fiber enters recall when the question names the day, not the summary."""

from dylan.memory.recall import recall


def test_time_window_injects_a_fiber_whose_text_is_absent(bare_store, make_fiber) -> None:
    fiber = make_fiber(
        bare_store,
        "旅行锚",
        summary="一次独自旅行",
        body="一次独自旅行",
        essence="一次独自旅行",
        time_start="2026-11-03T00:00:00Z",
        time_end="2026-11-04T00:00:00Z",
    )
    query = "2026-11-03 那天如何"
    assert "一次独自旅行" not in query
    result = recall(bare_store, query, depth=1, max_hops=2, window_days=7, persist=False)
    assert fiber.id in [hit.fiber.id for hit in result.hits]
