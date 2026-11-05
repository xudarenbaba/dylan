"""The desktop window's worker: same turn, no real window, no second writer."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from io import StringIO
from pathlib import Path

from dylan.config import Settings
from dylan.desk.session import SETTLING, DeskSession
from dylan.dialogue.loop import MASKED_NOTICE
from dylan.errors import NetworkError
from dylan.llm.fake import FakeModel
from dylan.memory.constants import PRIVACY_NOTICE
from dylan.memory.store import MemoryStore

ROOT = Path(__file__).resolve().parents[1]
LETTER = (ROOT / "persona" / "identity.md").read_text(encoding="utf-8")

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
    "mood": None,
    "summary": "他说了他的猫团子",
}


class GatedModel(FakeModel):
    """Yields one piece, then waits. Closing can only land on the next piece."""

    def __init__(self) -> None:
        super().__init__()
        self._gates: list[threading.Event] = []
        self.parts = ("半", "句")

    def gate(self, index: int) -> threading.Event:
        while len(self._gates) <= index:
            self._gates.append(threading.Event())
        return self._gates[index]

    def release_all(self) -> None:
        for gate in self._gates:
            gate.set()
        self.gate(0).set()

    def stream_reply(self, messages):
        index = len(self.seen)
        self.seen.append(messages)
        yield self.parts[0] if index == 0 else "丙"
        if not self.gate(index).wait(5):
            return
        yield self.parts[1] if index == 0 else "丁"


def _pull(session: DeskSession, found: list[dict[str, str]], ready, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found.extend(session.poll())
        if ready(found):
            return
        time.sleep(0.01)
    raise AssertionError(found)


def _open(tmp_path: Path, clock, model: FakeModel | None = None, **extra: object):
    db = tmp_path / "dylan.db"
    chosen = model if model is not None else FakeModel()
    err = StringIO()
    fields: dict[str, object] = {"deepseek_api_key": "test-key", "dylan_db": str(db)}
    fields.update(extra)
    settings = Settings(**fields)  # type: ignore[arg-type]
    session = DeskSession(
        path=db,
        clock=clock,
        letter=LETTER,
        model=chosen,
        settings=settings,
        stderr=err,
    )
    return session, chosen, err, db


def _stop(session: DeskSession, model: FakeModel) -> None:
    if isinstance(model, GatedModel):
        model.release_all()
    session.request_stop()
    session.join(5)
    assert not session.alive()


def test_missing_key_does_not_open_a_window(tmp_path: Path, invoke) -> None:
    assert "webview" not in sys.modules
    db = tmp_path / "missing" / "dylan.db"
    code, _out, err, model = invoke(db, argv=["desk"], key="")
    assert code == 1
    assert "DEEPSEEK_API_KEY" in err
    assert not db.exists()
    assert not db.parent.exists()
    assert model.seen == []
    assert "webview" not in sys.modules


def test_a_locked_brain_does_not_open_a_window(tmp_path: Path, invoke) -> None:
    db = tmp_path / "dylan.db"
    invoke(db, ["exit"])
    ready = tmp_path / "ready"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from dylan.cli.lock import BrainLock\n"
        "lock = BrainLock(Path(sys.argv[1]))\n"
        "lock.acquire()\n"
        "Path(sys.argv[2]).write_text('ready', encoding='utf-8')\n"
        "import time\n"
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
        code, _out, err, _model = invoke(db, argv=["desk"])
        assert code == 1
        assert "已有一个 dylan 在使用这块大脑" in err
        assert "webview" not in sys.modules
    finally:
        proc.kill()
        proc.wait(timeout=5)


def test_privacy_is_shown_once_and_blank_lines_do_nothing(tmp_path: Path, clock) -> None:
    session, model, _err, db = _open(tmp_path, clock)
    found: list[dict[str, str]] = []
    try:
        _pull(session, found, lambda ev: any(item["kind"] == "privacy" for item in ev))
        session.send("   ")
        session.send("")
        time.sleep(0.05)
        assert model.seen == []
        assert [item["text"] for item in found if item["kind"] == "privacy"] == [PRIVACY_NOTICE]
    finally:
        _stop(session, model)
    again, model, _err, _db = _open(tmp_path, clock, model)
    found = []
    try:
        again.send("你好")
        _pull(again, found, lambda ev: any(item["kind"] == "end" for item in ev))
        assert PRIVACY_NOTICE not in [item.get("text") for item in found]
        assert not any(item["kind"] == "privacy" for item in found)
    finally:
        _stop(again, model)
    assert db.exists()


def test_turns_run_one_at_a_time_and_sending_does_not_block(tmp_path: Path, clock) -> None:
    model = GatedModel()
    session, model, _err, _db = _open(tmp_path, clock, model)
    found: list[dict[str, str]] = []
    try:
        session.send("第一句")
        _pull(session, found, lambda ev: any(item.get("text") == "半" for item in ev))
        started = time.monotonic()
        session.send("第二句")
        assert time.monotonic() - started < 0.2
        time.sleep(0.05)
        assert len(model.seen) == 1
        model.gate(0).set()
        _pull(
            session,
            found,
            lambda ev: any(item.get("text") == "丙" for item in ev),
        )
        end_at = next(i for i, item in enumerate(found) if item["kind"] == "end")
        second_at = next(i for i, item in enumerate(found) if item.get("text") == "丙")
        assert end_at < second_at
        model.gate(1).set()
        _pull(session, found, lambda ev: sum(item["kind"] == "end" for item in ev) == 2)
    finally:
        _stop(session, model)


def test_closing_after_a_turn_sleeps_and_keeps_what_was_noted(tmp_path: Path, clock) -> None:
    model = FakeModel()
    model.notes = [_PET_NOTE]
    session, model, err, db = _open(tmp_path, clock, model)
    found: list[dict[str, str]] = []
    try:
        session.send("我养了一只猫叫团子")
        _pull(session, found, lambda ev: any(item["kind"] == "end" for item in ev))
        session.request_stop()
        _pull(session, found, lambda ev: any(item["kind"] == "closed" for item in ev))
        assert any(item.get("text") == SETTLING for item in found)
    finally:
        session.join(5)
    assert not session.alive()
    assert len(model.calls("note")) == 1
    assert len(model.calls("sleep")) == 1
    assert "我养了一只猫叫团子" in str(model.calls("sleep")[0])
    store = MemoryStore.open(db, clock)
    try:
        assert store.sessions()[0].slept
        assert store.counts()["turns"] == 0
        assert any(fiber.statement == "赵旭养了一只猫，叫团子" for fiber in store.fibers())
    finally:
        store.close()
    assert "〔" not in err.getvalue()


def test_closing_mid_reply_drops_that_turn_and_sleeps_the_earlier_one(
    tmp_path: Path, clock
) -> None:
    model = GatedModel()
    model.notes = [_PET_NOTE]
    session, model, _err, db = _open(tmp_path, clock, model)
    found: list[dict[str, str]] = []
    try:
        session.send("我养了一只猫叫团子")
        _pull(session, found, lambda ev: any(item.get("text") == "半" for item in ev))
        model.gate(0).set()
        _pull(session, found, lambda ev: any(item["kind"] == "end" for item in ev))
        session.send("请记住甲组的暗号")
        _pull(session, found, lambda ev: any(item.get("text") == "丙" for item in ev))
        session.request_stop()
        session.send("这句话不该再送出去")
        model.release_all()
        _pull(session, found, lambda ev: any(item["kind"] == "closed" for item in ev))
    finally:
        session.join(5)
    assert not session.alive()
    blob = str(model.calls("sleep"))
    assert "我养了一只猫叫团子" in blob
    assert "请记住甲组的暗号" not in blob
    assert "这句话不该再送出去" not in blob
    store = MemoryStore.open(db, clock)
    try:
        assert store.sessions()[0].slept
        assert not store.search_text("请记住甲组的暗号")
        assert not store.search_text("半")
        assert any(fiber.statement == "赵旭养了一只猫，叫团子" for fiber in store.fibers())
    finally:
        store.close()


def test_a_broken_reply_is_not_stored(tmp_path: Path, clock) -> None:
    model = FakeModel()
    model.partial = "半截"
    model.fail = NetworkError()
    session, model, err, db = _open(tmp_path, clock, model)
    found: list[dict[str, str]] = []
    try:
        session.send("请记住甲组的暗号")
        _pull(session, found, lambda ev: any(item["kind"] == "end" for item in ev))
        assert any(item.get("text") == "半截" for item in found)
        assert any(item.get("text") == "网络中断" for item in found)
        assert "网络中断" in err.getvalue()
    finally:
        _stop(session, model)
    assert not model.calls("sleep")
    assert not model.calls("note")
    store = MemoryStore.open(db, clock)
    try:
        assert not store.search_text("请记住甲组的暗号")
        assert not store.search_text("半截")
        assert store.sessions() == []
    finally:
        store.close()


def test_a_secret_is_hidden_in_the_window_and_on_the_terminal(tmp_path: Path, clock) -> None:
    token = "sk-" + "a" * 20
    model = FakeModel()
    session, model, err, _db = _open(tmp_path, clock, model, deepseek_api_key=token)
    found: list[dict[str, str]] = []
    try:
        session.send(f"请帮我存一下 {token} 好吗")
        _pull(session, found, lambda ev: any(item["kind"] == "end" for item in ev))
        assert any(item.get("text") == MASKED_NOTICE for item in found)
        assert all(token not in item.get("text", "") for item in found)
        assert MASKED_NOTICE in err.getvalue()
        assert token not in err.getvalue()
        sent = " ".join(message.get("content", "") for batch in model.seen for message in batch)
        assert token not in sent
    finally:
        _stop(session, model)


def test_mind_stays_on_the_terminal(tmp_path: Path, clock) -> None:
    session, model, err, _db = _open(tmp_path, clock, dylan_show_mind=True)
    found: list[dict[str, str]] = []
    try:
        session.send("你好")
        _pull(session, found, lambda ev: any(item["kind"] == "end" for item in ev))
        assert "〔常驻〕" in err.getvalue()
        assert all(not item.get("text", "").startswith("〔") for item in found)
        assert all("〔常驻〕" not in item.get("text", "") for item in found)
    finally:
        _stop(session, model)


def test_a_changed_letter_is_only_mentioned(tmp_path: Path, clock) -> None:
    session, model, _err, db = _open(tmp_path, clock)
    try:
        _pull(session, [], lambda ev: any(item["kind"] == "privacy" for item in ev))
    finally:
        _stop(session, model)
    fresh = FakeModel()
    err = StringIO()
    session = DeskSession(
        path=db,
        clock=clock,
        letter="dylan：\n我是赵旭。你最喜欢下雨天。",
        model=fresh,
        settings=Settings(deepseek_api_key="test-key"),
        stderr=err,
    )
    found: list[dict[str, str]] = []
    try:
        _pull(session, found, lambda ev: any(item["kind"] == "notice" for item in ev))
        assert any("身份信和她出生时读到的不一样了" in item.get("text", "") for item in found)
        assert "身份信和她出生时读到的不一样了" in err.getvalue()
        assert not fresh.calls("birth")
    finally:
        _stop(session, fresh)


def test_an_old_brain_is_refused_in_the_window(tmp_path: Path, clock) -> None:
    db = tmp_path / "dylan.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE meta (id INTEGER PRIMARY KEY, schema_version INTEGER, brain_name TEXT)"
    )
    conn.execute("INSERT INTO meta VALUES (1, 1, 'dylan')")
    conn.commit()
    conn.close()
    before = db.read_bytes()
    session, model, err, _db = _open(tmp_path, clock)
    found: list[dict[str, str]] = []
    try:
        _pull(session, found, lambda ev: any(item["kind"] == "closed" for item in ev))
        assert any("版本过旧" in item.get("text", "") for item in found)
        assert "版本过旧" in err.getvalue()
        assert "sk-" not in err.getvalue()
    finally:
        _stop(session, model)
    assert db.read_bytes() == before


def test_the_page_is_local_and_text_can_be_selected() -> None:
    html = (ROOT / "src" / "dylan" / "desk" / "page.html").read_text(encoding="utf-8")
    window = (ROOT / "src" / "dylan" / "desk" / "window.py").read_text(encoding="utf-8")
    session = (ROOT / "src" / "dylan" / "desk" / "session.py").read_text(encoding="utf-8")
    assert "<script src=" not in html
    assert "innerHTML" not in html
    assert "http://" not in html and "https://" not in html
    assert "clipboard" not in html.lower()
    assert "isComposing" in html and "shiftKey" in html and "textContent" in html
    assert "text_select=True" in window
    assert "on_top=False" in window and "fullscreen=False" in window
    assert "min_size=(300, 400)" in window
    assert "webview" not in session
    assert "sqlite3" not in session
