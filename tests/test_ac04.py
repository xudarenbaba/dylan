"""AC-04: closing the file and opening it again keeps the same identity and recall."""

from pathlib import Path

from dylan.memory.recall import recall
from dylan.memory.store import MemoryStore


def test_reopen_recalls_without_rewriting_identity(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["我喜欢深夜写代码"])
    first = MemoryStore.open(db, clock)
    try:
        identity = next(fiber for fiber in first.fibers() if fiber.memory_type == "identity")
        identity_id = identity.id
        identity_body = identity.body
    finally:
        first.close()
    second = MemoryStore.open(db, clock)
    try:
        again = next(fiber for fiber in second.fibers() if fiber.memory_type == "identity")
        assert again.id == identity_id
        assert again.body == identity_body
        assert len([fiber for fiber in second.fibers() if fiber.memory_type == "identity"]) == 1
        result = recall(
            second,
            "我晚上适合做什么",
            depth=1,
            max_hops=2,
            window_days=7,
            persist=False,
        )
        assert result.certainty != "none"
    finally:
        second.close()
