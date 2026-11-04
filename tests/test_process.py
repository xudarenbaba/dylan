"""Process edges: blank lines, exit consolidation, Ctrl-C, lock, and corrupt files."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from dylan.dialogue.rules import extract_rules
from dylan.memory.encode import bootstrap, write_drafts
from dylan.memory.store import MemoryStore
from support.identity import TEXT

ROOT = Path(__file__).resolve().parents[1]


def test_blank_line_then_exit_returns_zero(tmp_path: Path, invoke) -> None:
    code, _out, err, _model = invoke(tmp_path / "dylan.db", ["", "exit"])
    assert code == 0, err


def test_exit_runs_short_consolidation(tmp_path: Path, clock, invoke, make_fiber) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    make_fiber(store, "甲", summary="重复的偏好句子甲组", body="重复的偏好句子甲组")
    make_fiber(store, "乙", summary="重复的偏好句子甲组", body="重复的偏好句子甲组")
    store.close()
    code, _out, err, _model = invoke(db, ["", "exit"])
    assert code == 0, err
    store = MemoryStore.open(db, clock)
    try:
        states = sorted(
            fiber.state
            for fiber in store.fibers()
            if fiber.summary == "重复的偏好句子甲组"
        )
        assert states == ["active", "soft_deleted"]
    finally:
        store.close()


def test_keyboard_interrupt_skips_consolidation(tmp_path: Path, clock, invoke, make_fiber) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    make_fiber(store, "甲", summary="重复的偏好句子甲组", body="重复的偏好句子甲组")
    make_fiber(store, "乙", summary="重复的偏好句子甲组", body="重复的偏好句子甲组")
    store.close()

    class Interrupting:
        def readline(self) -> str:
            raise KeyboardInterrupt

    code, _out, _err, _model = invoke(db, stdin=Interrupting())
    assert code == 130
    store = MemoryStore.open(db, clock)
    try:
        states = [
            fiber.state
            for fiber in store.fibers()
            if fiber.summary == "重复的偏好句子甲组"
        ]
        assert states == ["active", "active"]
        assert not any(fiber.auto_session for fiber in store.fibers())
    finally:
        store.close()


def test_second_process_is_locked_out(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    store.close()
    ready = tmp_path / "ready"
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from dylan.cli.lock import BrainLock\n"
        "lock = BrainLock(Path(sys.argv[1]))\n"
        "lock.acquire()\n"
        "Path(sys.argv[2]).write_text('ready', encoding='utf-8')\n"
        "time.sleep(30)\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(db) + ".lock", str(ready)],
        env=env,
    )
    try:
        for _ in range(100):
            if ready.exists():
                break
            if proc.poll() is not None:
                raise AssertionError("lock holder exited early")
            time.sleep(0.05)
        else:
            raise AssertionError("lock was not acquired")
        code, _out, err, _model = invoke(db, argv=["status"], key="")
        assert code == 1
        assert "已有一个 dylan 在使用这块大脑" in err
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_corrupt_file_is_left_unchanged(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    db.write_bytes(b"this is not a database")
    before = db.read_bytes()
    code, _out, err, _model = invoke(db, argv=["status"], key="")
    assert code != 0
    assert "记忆库损坏" in err
    assert db.read_bytes() == before


def test_missing_database_is_not_created(tmp_path: Path, invoke) -> None:
    db = tmp_path / "missing" / "dylan.db"
    code, _out, err, _model = invoke(db, argv=["status"], key="")
    assert code != 0
    assert "记忆库不存在" in err
    assert "DEEPSEEK_API_KEY" not in err
    assert not db.exists()
    assert not db.parent.exists()


def test_higher_schema_is_refused_and_kept(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    store.close()
    _set_meta(db, "schema_version", 99)
    code, _out, err, _model = invoke(db, argv=["status"], key="")
    assert code != 0
    assert "记忆库损坏" in err
    assert _meta(db, "schema_version") == 99


def test_older_schema_is_refused(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    store.close()
    _set_meta(db, "schema_version", 0)
    code, _out, err, _model = invoke(db, argv=["status"], key="")
    assert code != 0
    assert "记忆库损坏" in err
    assert _meta(db, "schema_version") == 0


def test_foreign_brain_name_is_refused(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    store.close()
    _set_meta(db, "brain_name", "other")
    code, _out, err, _model = invoke(db, argv=["status"], key="")
    assert code != 0
    assert "记忆库损坏" in err
    assert _meta(db, "brain_name") == "other"


def test_missing_identity_asks_for_reset(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    store.close()
    code, _out, err, _model = invoke(db, ["你好"])
    assert code != 0
    assert "reset-identity" in err
    store = MemoryStore.open(db, clock)
    try:
        assert not store.identity_pinned()
    finally:
        store.close()


def test_consolidate_needs_exactly_one_selector(tmp_path: Path, invoke) -> None:
    db = tmp_path / "missing" / "dylan.db"
    code, _out, err, _model = invoke(db, argv=["consolidate"], key="")
    assert code == 1
    assert "需要 --strategy 或 --all" in err
    assert not db.exists()
    code, _out, err, _model = invoke(
        db,
        argv=["consolidate", "--all", "--strategy", "prune"],
        key="",
    )
    assert code == 1
    assert "需要 --strategy 或 --all" in err


def test_revision_phrases_keep_both_sides(store) -> None:
    write_drafts(store, extract_rules("我决定用红色")[0])
    write_drafts(store, extract_rules("改成用蓝色")[0])
    decisions = [
        fiber
        for fiber in store.fibers()
        if fiber.memory_type == "decision" and fiber.state == "active"
    ]
    assert len(decisions) == 2
    assert any(synapse.type == "evolves_from" for synapse in store.synapses())


def test_model_inference_is_not_stored_as_something_the_user_said(
    tmp_path: Path, clock, invoke
) -> None:
    from dylan.llm.fake import FakeModel

    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.json_items = [
        {
            "memory_type": "fact",
            "summary": "用户心情稳定",
            "neurons": [{"kind": "concept", "content": "用户心情稳定"}],
            "links": [],
        },
        {
            "memory_type": "not_a_type",
            "summary": "这条类型不存在",
            "neurons": [{"kind": "concept", "content": "这条类型不存在"}],
            "links": [],
        },
    ]
    invoke(db, ["今天还好"], model=model)
    store = MemoryStore.open(db, clock)
    try:
        invented = [fiber for fiber in store.fibers() if fiber.summary == "用户心情稳定"]
        assert len(invented) == 1
        assert invented[0].provenance.source == "ai_inference"
        assert invented[0].provenance.confidence == "medium"
        assert invented[0].provenance.trust <= 0.7
        assert not any(fiber.summary == "这条类型不存在" for fiber in store.fibers())
    finally:
        store.close()


def _set_meta(path: Path, column: str, value: object) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"UPDATE meta SET {column} = ? WHERE id = 1", (value,))
        conn.commit()
    finally:
        conn.close()


def _meta(path: Path, column: str) -> object:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(f"SELECT {column} FROM meta WHERE id = 1").fetchone()
    finally:
        conn.close()
    return row[0]
