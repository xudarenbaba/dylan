"""The memory page reads one brain without creating or locking it."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import urlopen

from conftest import LETTER, TZ
from dylan.cli.lock import BrainLock
from dylan.llm.fake import FakeModel
from dylan.memory.life import birth
from dylan.memory.store import MemoryStore
from dylan.viz.server import make_server


def test_page_reads_graph_memories_and_journal_without_the_writer_lock(
    tmp_path: Path, clock
) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    birth(store, LETTER, FakeModel().default_birth(LETTER), TZ)
    store.close()
    lock = BrainLock(Path(str(db) + ".lock"))
    lock.acquire()
    httpd = make_server(db, "127.0.0.1", 0, TZ)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with urlopen(base + "/api/graph", timeout=5) as response:
            graph = json.load(response)
        assert any(node["name"] == "赵旭" and node["is_user"] for node in graph["nodes"])
        assert any(memory["type"] == "天生" for memory in graph["memories"])
        assert graph["journal"]
        assert graph["mind"]["baseline_mood"] == "开朗"
        with urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "只读" in page and "Simple Browser" in page
    finally:
        httpd.shutdown()
        thread.join(timeout=3)
        httpd.server_close()
        lock.release()
