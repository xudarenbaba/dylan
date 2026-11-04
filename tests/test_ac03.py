"""AC-03: a later question reaches 深夜 through the time-word edge."""

from pathlib import Path

from dylan.llm.fake import _read_thought
from dylan.memory.store import MemoryStore


def test_evening_question_recalls_the_late_night_preference(
    tmp_path: Path, clock, invoke
) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["我喜欢深夜写代码"])
    store = MemoryStore.open(db, clock)
    try:
        preference = next(fiber for fiber in store.fibers() if fiber.memory_type == "preference")
        contents = [store.neuron(neuron_id).content for neuron_id in preference.neuron_ids]
        assert "深夜" in contents
        assert preference.body == "我喜欢深夜写代码"
    finally:
        store.close()
    _code, _out, err, model = invoke(db, ["我晚上适合做什么"])
    assert "这一轮没有记住" not in err
    thought = _read_thought(model.seen[-1])
    assert thought["certainty"] != "none"
    summaries = [str(item["summary"]) for item in thought["recalled"]]  # type: ignore[index]
    assert any("深夜" in summary or "我喜欢深夜写代码" in summary for summary in summaries)
