"""AC-30: hypothesis confidence rises with support and falls with opposition."""

import pytest

from dylan.memory.encode import Draft, add_evidence, write_draft


def test_evidence_moves_confidence_up_then_down(store) -> None:
    hypothesis = write_draft(
        store,
        Draft(
            memory_type="hypothesis",
            summary="甲组会成功",
            body="甲组会成功",
            neurons=[("concept", "甲组会成功")],
        ),
    )
    assert hypothesis is not None
    assert hypothesis.confidence_value == pytest.approx(0.5)
    supported = add_evidence(store, hypothesis, support=True, text="看到了进展")
    assert supported.confidence_value == pytest.approx(0.55)
    opposed = add_evidence(store, supported, support=False, text="后来停滞")
    assert opposed.confidence_value == pytest.approx(0.44)
