"""AC-10: an sk- token is dropped before it can be written."""

import json
from pathlib import Path

from dylan.llm.fake import _read_thought
from dylan.memory.store import MemoryStore

_TOKEN = "sk-abcdefghijklmnopqrst"


def test_secret_token_is_absent_from_the_store_and_the_warning(
    tmp_path: Path, clock, invoke
) -> None:
    db = tmp_path / "dylan.db"
    _code, _out, err, model = invoke(db, [f"我喜欢{_TOKEN}写代码"])
    assert "这则内容没有记住" in err
    assert _TOKEN not in err
    thought = _read_thought(model.seen[-1])
    assert _TOKEN not in json.dumps(thought, ensure_ascii=False)
    store = MemoryStore.open(db, clock)
    try:
        assert not store.search_text(_TOKEN)
    finally:
        store.close()
