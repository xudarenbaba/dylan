"""AC-06: three distinct dates promote a preference; a one-shot context falls behind."""

from dylan.memory.decay import apply_decay
from dylan.memory.encode import Draft, write_draft
from dylan.memory.recall import recall

_PREFERENCE = "我喜欢甲组的安排"


def test_rehearsed_preference_outlasts_a_single_context(store, clock) -> None:
    draft = Draft(
        memory_type="preference",
        summary=_PREFERENCE,
        body=_PREFERENCE,
        neurons=[("entity", "甲组"), ("concept", _PREFERENCE)],
    )
    write_draft(store, draft)
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
    clock.advance(days=1)
    write_draft(store, draft)
    clock.advance(days=1)
    preference = write_draft(store, draft)
    assert preference is not None
    assert preference.stage == "working"
    clock.advance(days=14)
    apply_decay(store)
    preference = store.fiber(preference.id)
    context = store.fiber(context.id)
    assert preference is not None and context is not None
    assert preference.stage == "working"
    assert preference.conductivity > context.conductivity
    result = recall(store, _PREFERENCE, depth=1, max_hops=2, window_days=7, persist=False)
    hit_ids = [hit.fiber.id for hit in result.hits]
    assert preference.id in hit_ids
    assert context.id not in hit_ids
    matched = next(hit for hit in result.hits if hit.fiber.id == preference.id)
    assert matched.certainty in {"faint", "clear"}
    assert matched.score >= 0.2
