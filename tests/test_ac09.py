"""AC-09: the same preference rehearses one fiber instead of inserting another."""

from pathlib import Path

from dylan.memory.store import MemoryStore


def test_repeated_preference_does_not_insert_a_second_fiber(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["我喜欢深夜写代码", "我喜欢深夜写代码"])
    store = MemoryStore.open(db, clock)
    try:
        matches = [
            fiber
            for fiber in store.fibers()
            if fiber.memory_type == "preference" and fiber.state == "active"
        ]
        assert len(matches) == 1
        assert matches[0].rehearsal_count >= 1
        assert matches[0].frequency >= 2
    finally:
        store.close()
