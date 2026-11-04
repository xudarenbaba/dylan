"""AC-21: an expired context stays in the file until the grace window ends."""

from dylan.memory.encode import Draft, write_draft
from dylan.memory.prune import prune
from dylan.memory.recall import recall


def test_expired_context_is_hidden_then_removed_after_grace(store, clock) -> None:
    context = write_draft(
        store,
        Draft(
            memory_type="context",
            summary="今天下雨了",
            body="今天下雨了",
            neurons=[("concept", "今天下雨了")],
        ),
    )
    assert context is not None
    expires_at = context.expires_at
    clock.advance(days=8)
    result = recall(store, "今天下雨了", depth=1, max_hops=2, window_days=7)
    assert context.id not in [hit.fiber.id for hit in result.hits]
    hidden = store.fiber(context.id)
    assert hidden is not None
    assert hidden.state == "soft_deleted"
    assert hidden.deleted_at == expires_at
    clock.advance(days=8)
    prune(store)
    assert store.fiber(context.id) is None
