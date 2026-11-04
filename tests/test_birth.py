"""Birth from the letter, and replacing only what she was born with."""

from __future__ import annotations

from pathlib import Path

from conftest import LETTER, TZ, fact
from dylan.llm.fake import FakeModel
from dylan.memory.life import birth, letter_changed, reset_innate
from dylan.memory.store import MemoryStore


def test_birth_writes_innate_memories_from_the_letter(store) -> None:
    meta = store.meta()
    assert store.born()
    assert meta["identity_text"] == LETTER.strip()
    assert store.neuron(meta["self_id"]).name == "dylan"
    assert store.neuron(meta["user_id"]).name == "赵旭"
    innate = [fiber for fiber in store.fibers() if fiber.memory_type == "innate"]
    assert innate
    assert all(fiber.source == "innate" and fiber.stage == "settled" for fiber in innate)
    assert any("乐观、开朗、温柔" in fiber.statement for fiber in innate)
    assert any("二十岁" in fiber.statement for fiber in innate)
    assert meta["baseline_mood"] == "开朗"


def test_birth_rejects_what_the_letter_does_not_say(bare_store) -> None:
    proposal = FakeModel().default_birth(LETTER)
    proposal["ops"].append(
        {"op": "add", "statement": "dylan 其实是男性", "evidence": "dylan 其实是男性"}
    )
    outcome = birth(bare_store, LETTER, proposal, TZ)
    assert outcome.rejected == 1
    assert not any("男性" in fiber.statement for fiber in bare_store.fibers())


def test_innate_memories_cannot_be_changed_in_conversation(store, note) -> None:
    innate = next(fiber for fiber in store.fibers() if fiber.memory_type == "innate")
    outcome = note(
        [
            {"op": "suppress", "target": "m1"},
            {"op": "update", "target": "m1", "statement": "她其实不开朗"},
            {"op": "add", "type": "innate", "statement": "她是男性", "evidence": "她是男性"},
        ],
        user_text="她是男性",
        shown=[innate],
    )
    assert outcome.rejected == 3
    again = store.fiber(innate.id)
    assert again.state == "active" and again.statement == innate.statement


def test_letter_change_is_noticed_but_not_applied(store) -> None:
    assert not letter_changed(store, LETTER)
    assert letter_changed(store, LETTER + "\n你最喜欢猫。")
    assert store.meta()["identity_text"] == LETTER.strip()


def test_reset_replaces_only_the_innate_self(store, note) -> None:
    note([fact("赵旭养了一只猫，叫团子", "我养了一只猫叫团子")], user_text="我养了一只猫叫团子")
    letter = LETTER + "\n你最喜欢下雨天。"
    reset_innate(store, letter, FakeModel().default_birth(letter), TZ)
    innate = [fiber for fiber in store.fibers() if fiber.memory_type == "innate"]
    assert any("下雨天" in fiber.statement for fiber in innate)
    assert any(fiber.statement == "赵旭养了一只猫，叫团子" for fiber in store.fibers())
    assert store.meta()["identity_text"] == letter.strip()


def test_failed_birth_leaves_no_brain(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.births = [{"user_name": "", "ops": []}]
    code, _out, err, _model = invoke(db, ["你好", "exit"], model=model)
    assert code == 1
    assert "出生失败" in err
    assert not db.exists()


def test_second_start_does_not_rebirth(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    store = MemoryStore.open(db, clock)
    first = sorted(fiber.id for fiber in store.fibers() if fiber.memory_type == "innate")
    store.close()
    _code, _out, _err, model = invoke(db, ["exit"])
    assert not model.calls("birth")
    store = MemoryStore.open(db, clock)
    try:
        again = sorted(fiber.id for fiber in store.fibers() if fiber.memory_type == "innate")
        assert again == first
    finally:
        store.close()
