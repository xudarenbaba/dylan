"""AC-12: past the twelfth stored turn, the first fact comes back from long-term memory."""

from pathlib import Path

from dylan.llm.fake import _read_thought
from dylan.memory.store import MemoryStore


def test_first_fact_survives_after_the_buffer_spills(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    lines = ["我喜欢苹果", *["你好"] * 12, "我喜欢苹果吗"]
    _code, out, _err, model = invoke(db, lines)
    past = [
        message["content"]
        for message in model.seen[-1]
        if message["content"].startswith("刚才的对话")
    ]
    assert past
    assert all("我喜欢苹果" not in message for message in past)
    thought = _read_thought(model.seen[-1])
    summaries = " ".join(str(item["summary"]) for item in thought["recalled"])  # type: ignore[index]
    assert "我喜欢苹果" in summaries or "我喜欢苹果" in out
    store = MemoryStore.open(db, clock)
    try:
        active = [
            fiber
            for fiber in store.fibers()
            if fiber.state == "active" and "我喜欢苹果" in (fiber.body or fiber.summary)
        ]
        assert active
    finally:
        store.close()
