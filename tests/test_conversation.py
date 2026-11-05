"""The whole loop: reply prompt, noting in the background, sleep, and next time."""

from __future__ import annotations

from pathlib import Path

from dylan.llm.fake import FakeModel
from dylan.memory.constants import PRIVACY_NOTICE
from dylan.memory.store import MemoryStore

_PET_NOTE = {
    "ops": [
        {
            "op": "add",
            "type": "fact",
            "about": "赵旭",
            "statement": "赵旭养了一只猫，叫团子",
            "evidence": "我养了一只猫叫团子",
            "source": "user",
            "nodes": [{"name": "团子", "kind": "animal", "aliases": ["猫"]}],
            "cues": ["团子"],
        }
    ],
    "used": [],
    "mood": {"label": "开心", "intensity": 0.6, "cause": "他说了团子"},
    "summary": "他说了他的猫团子",
}


def _open(db: Path, clock) -> MemoryStore:
    return MemoryStore.open(db, clock)


def test_first_start_is_born_and_prints_privacy_once(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    code, out, err, model = invoke(db, ["exit"])
    assert code == 0, err
    assert out.splitlines()[0] == PRIVACY_NOTICE
    assert len(model.calls("birth")) == 1
    _code, out, _err, _model = invoke(db, ["exit"])
    assert PRIVACY_NOTICE not in out


def test_reply_sees_the_letter_awareness_and_recall(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.notes = [_PET_NOTE]
    invoke(db, ["我养了一只猫叫团子", "团子今天好调皮", "exit"], model=model)
    second = model.seen[1]
    assert second[0]["content"].startswith("dylan：")
    mind = second[1]["content"]
    assert "现在是" in mind and "不要编" in mind
    assert "赵旭养了一只猫，叫团子" in mind
    assert second[2] == {"role": "user", "content": "我养了一只猫叫团子"}
    assert second[-1] == {"role": "user", "content": "团子今天好调皮"}


def test_noting_happens_after_the_reply_and_sleep_after_exit(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.notes = [_PET_NOTE]
    code, _out, err, model = invoke(db, ["我养了一只猫叫团子", "exit"], model=model)
    assert code == 0, err
    assert len(model.calls("note")) == 1
    assert len(model.calls("sleep")) == 1
    store = _open(db, clock)
    try:
        types = [fiber.memory_type for fiber in store.fibers() if fiber.memory_type != "innate"]
        assert sorted(types) == ["fact", "session"]
        assert store.counts()["turns"] == 0
        assert store.sessions()[0].slept
        assert store.mood().label == "开心"
    finally:
        store.close()


def test_next_conversation_remembers_last_time(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.notes = [_PET_NOTE]
    model.sleeps = [
        {
            "ops": [
                {
                    "op": "add",
                    "type": "session",
                    "statement": "我们第一次聊天，他说起了他的猫团子",
                    "source": "shared",
                }
            ],
            "summary": "第一次聊天，他说起了猫团子",
            "mood": None,
        }
    ]
    invoke(db, ["我养了一只猫叫团子", "exit"], model=model)
    clock.advance(days=2)
    model.reply = "嗯嗯"
    invoke(db, ["我回来啦", "exit"], model=model)
    mind = model.seen[-1][1]["content"]
    assert "上次聊天：第一次聊天，他说起了猫团子" in mind
    assert "过去了大约 2 天" in mind
    assert "赵旭养了一只猫，叫团子" in mind


def test_a_failed_note_is_retried_before_sleep(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.notes = [RuntimeError("down"), _PET_NOTE]
    code, _out, err, model = invoke(db, ["我养了一只猫叫团子", "嗯", "exit"], model=model)
    assert code == 0
    assert "上一轮没有记下来" in err
    store = _open(db, clock)
    try:
        assert any(fiber.statement == "赵旭养了一只猫，叫团子" for fiber in store.fibers())
    finally:
        store.close()


def test_a_failed_sleep_is_finished_on_the_next_start(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.notes = [_PET_NOTE]
    model.sleeps = [RuntimeError("down")]
    code, _out, err, _model = invoke(db, ["我养了一只猫叫团子", "exit"], model=model)
    assert code == 0
    assert "睡眠整理没有完成" in err
    store = _open(db, clock)
    try:
        assert not store.sessions()[0].slept
        assert store.counts()["turns"] == 1
    finally:
        store.close()
    invoke(db, ["exit"], model=model)
    store = _open(db, clock)
    try:
        assert all(session.slept for session in store.sessions())
        assert any(fiber.memory_type == "session" for fiber in store.fibers())
    finally:
        store.close()


def test_a_secret_in_what_he_says_is_masked(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    token = "sk-" + "a1b2c3d4e5f6g7h8i9j0"
    code, _out, err, model = invoke(db, [f"我的密钥是 {token}", "exit"])
    assert code == 0
    assert "像密钥的部分没有记住" in err
    assert token not in str(model.seen)
    for kind, messages in model.json_seen:
        assert token not in str(messages), kind
    store = _open(db, clock)
    try:
        assert not store.search_text(token)
    finally:
        store.close()


def test_show_mind_prints_awareness_and_notes_to_stderr(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.notes = [_PET_NOTE]
    _code, out, err, _model = invoke(
        db, ["我养了一只猫叫团子", "exit"], model=model, show_mind=True
    )
    assert "〔常驻〕" in err and "〔记下〕" in err and "〔睡眠〕" in err
    assert "〔常驻〕" not in out
