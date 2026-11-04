"""Process edges: blank lines, Ctrl-C, the lock, corrupt or old files, missing brains."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from dylan.memory.store import MemoryStore

ROOT = Path(__file__).resolve().parents[1]


def test_blank_line_then_exit_returns_zero(tmp_path: Path, invoke) -> None:
    code, _out, err, _model = invoke(tmp_path / "dylan.db", ["", "exit"])
    assert code == 0, err


def test_missing_key_refuses_before_creating_a_brain(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    code, _out, err, _model = invoke(db, ["你好"], key="")
    assert code == 1
    assert "DEEPSEEK_API_KEY" in err
    assert not db.exists()


def test_keyboard_interrupt_skips_sleep(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])

    class Interrupting:
        def __init__(self) -> None:
            self.lines = ["你好\n"]

        def readline(self) -> str:
            if self.lines:
                return self.lines.pop()
            raise KeyboardInterrupt

    code, _out, _err, model = invoke(db, stdin=Interrupting())
    assert code == 130
    assert not model.calls("sleep")
    store = MemoryStore.open(db, clock)
    try:
        assert any(not session.slept for session in store.sessions())
    finally:
        store.close()


def test_second_process_is_locked_out(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
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
    proc = subprocess.Popen([sys.executable, "-c", script, str(db) + ".lock", str(ready)], env=env)
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
    for argv in (["status"], ["maintain"], ["memory"]):
        code, _out, err, _model = invoke(db, argv=argv, key="")
        assert code != 0
        assert "记忆库不存在" in err
    assert not db.parent.exists()


def test_an_old_brain_is_refused_and_kept(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE meta (id INTEGER PRIMARY KEY, schema_version INTEGER, brain_name TEXT)"
    )
    conn.execute("INSERT INTO meta VALUES (1, 1, 'dylan')")
    conn.commit()
    conn.close()
    before = db.read_bytes()
    code, _out, err, _model = invoke(db, ["你好"])
    assert code != 0
    assert "版本过旧" in err and "备份" in err
    assert db.read_bytes() == before


def test_a_higher_or_foreign_brain_is_refused(tmp_path: Path, clock, invoke) -> None:
    for column, value in (("schema_version", 99), ("brain_name", "other")):
        db = tmp_path / f"{column}.db"
        MemoryStore.create(db, clock).close()
        conn = sqlite3.connect(db)
        conn.execute(f"UPDATE meta SET {column} = ? WHERE id = 1", (value,))
        conn.commit()
        conn.close()
        code, _out, err, _model = invoke(db, argv=["status"], key="")
        assert code != 0
        assert "记忆库损坏" in err


def test_status_and_maintain_need_no_key(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    code, out, err, model = invoke(db, argv=["status"], key="")
    assert code == 0, err
    assert "出生：是" in out
    code, out, err, _model = invoke(db, argv=["maintain"], key="")
    assert code == 0, err
    assert not model.json_seen


def test_reset_identity_needs_yes_and_keeps_her_life(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    code, _out, err, _model = invoke(db, argv=["reset-identity"])
    assert code == 1 and "需要 --yes" in err
    letter = tmp_path / "identity.md"
    letter.write_text("dylan：\n我是赵旭。你叫 dylan，你最喜欢下雨天。", encoding="utf-8")
    code, out, err, _model = invoke(db, argv=["reset-identity", "--yes"], identity_path=letter)
    assert code == 0, err
    assert "天性已重写" in out
    store = MemoryStore.open(db, clock)
    try:
        innate = [fiber.statement for fiber in store.fibers() if fiber.memory_type == "innate"]
        assert any("下雨天" in statement for statement in innate)
        assert not any("乐观" in statement for statement in innate)
    finally:
        store.close()


def test_a_changed_letter_is_only_mentioned(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    letter = tmp_path / "identity.md"
    letter.write_text("dylan：\n我是赵旭。你最喜欢下雨天。", encoding="utf-8")
    code, _out, err, model = invoke(db, ["exit"], identity_path=letter)
    assert code == 0
    assert "身份信和她出生时读到的不一样了" in err
    assert not model.calls("birth")
