"""AC-02: first start pins identity and says the conversation leaves the machine."""

from pathlib import Path

from dylan.memory.constants import PRIVACY_NOTICE
from dylan.memory.store import MemoryStore
from support.identity import TEXT


def test_first_start_pins_identity_and_prints_privacy(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    code, out, err, _model = invoke(db, ["exit"])
    assert code == 0
    assert err == ""
    assert out.splitlines()[0] == PRIVACY_NOTICE
    store = MemoryStore.open(db, clock)
    try:
        pinned = [fiber for fiber in store.fibers() if fiber.memory_type == "identity"]
        assert len(pinned) == 1
        assert pinned[0].pinned
        assert "dylan" in (pinned[0].body or "")
        assert "没有印象" in (pinned[0].body or "")
        assert "屏幕" in (pinned[0].body or "")
    finally:
        store.close()


def test_second_open_does_not_reseed_or_repeat_privacy(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    store = MemoryStore.open(db, clock)
    try:
        first = next(fiber.id for fiber in store.fibers() if fiber.memory_type == "identity")
    finally:
        store.close()
    _code, out, _err, _model = invoke(db, ["exit"])
    assert PRIVACY_NOTICE not in out
    store = MemoryStore.open(db, clock)
    try:
        pinned = [fiber for fiber in store.fibers() if fiber.memory_type == "identity"]
        assert [fiber.id for fiber in pinned] == [first]
    finally:
        store.close()


def test_reset_without_yes_refuses_before_changing_identity(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    code, _out, err, _model = invoke(db, argv=["reset-identity"], key="")
    assert code == 1
    assert "拒绝执行：需要 --yes" in err
    store = MemoryStore.open(db, clock)
    try:
        body = next(fiber.body for fiber in store.fibers() if fiber.memory_type == "identity")
        assert body == TEXT
    finally:
        store.close()


def test_reset_yes_rewrites_identity_and_keeps_user_memory(
    tmp_path: Path, clock, invoke, make_fiber
) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    from dylan.memory.encode import bootstrap

    bootstrap(store, TEXT)
    user = make_fiber(store, "用户保留的事实甲组", summary="用户保留的事实甲组")
    store.close()
    replacement = tmp_path / "identity.md"
    replacement.write_text("新的身份种子甲组。他仍然没有身体。", encoding="utf-8")
    code, out, err, _model = invoke(
        db,
        argv=["reset-identity", "--yes"],
        key="",
        identity_path=replacement,
    )
    assert code == 0, err
    assert "身份已重写" in out
    store = MemoryStore.open(db, clock)
    try:
        bodies = [fiber.body for fiber in store.fibers() if fiber.memory_type == "identity"]
        assert bodies == ["新的身份种子甲组。他仍然没有身体。"]
        kept = store.fiber(user.id)
        assert kept is not None
        assert kept.state == "active"
        assert kept.summary == "用户保留的事实甲组"
    finally:
        store.close()
