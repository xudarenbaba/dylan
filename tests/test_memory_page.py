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
        groups = {
            "element": "成分",
            "social": "社会",
            "possession": "拥有",
            "attitude": "态度",
            "sequence": "先后",
            "revision": "修订",
            "grown": "一起被想起",
        }
        assert graph["links"]
        for link in graph["links"]:
            assert link["group"] in groups
            assert link["group_label"] == groups[link["group"]]
        with urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "只读" in page and "Simple Browser" in page
        for word in ("放大", "缩小", "看全图", "图例", "只留相连"):
            assert word in page
        assert "<script src=" not in page
    finally:
        httpd.shutdown()
        thread.join(timeout=3)
        httpd.server_close()
        lock.release()
