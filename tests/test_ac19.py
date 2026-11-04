"""AC-19: a 40-day tier-2 fiber sends its essence, and the two budgets stay separate."""

from pathlib import Path

from dylan.dialogue.buffer import Buffer
from dylan.dialogue.prompt import build_messages, pack_hot, pack_recall
from dylan.dialogue.thought import Thought
from dylan.memory.encode import bootstrap
from dylan.memory.store import MemoryStore
from support.identity import TEXT

_BODY = "FULLBODY_MARKER这是全文"
_ESSENCE = "ESSENCE_MARKER"


def test_old_tier_two_fiber_sends_essence_not_the_body(
    tmp_path: Path, clock, invoke, make_fiber
) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    make_fiber(
        store,
        "甲组",
        kind="entity",
        summary="短摘要",
        body=_BODY,
        essence=_ESSENCE,
        ghost="残影",
        compression_tier=2,
        created_at="2026-09-24T00:00:00Z",
    )
    store.close()
    _code, _out, _err, model = invoke(db, ["甲组近况"])
    prompt = "\n".join(message["content"] for message in model.seen[-1])
    assert _ESSENCE in prompt
    assert _BODY not in prompt
    assert "遵守思考记录里的态度" in prompt
    assert "推断必须说是推断" in prompt
    assert "没有印象就说没有印象" in prompt
    assert "冲突要同时承认两边" in prompt
    assert "可见回答不使用内部字段名" in prompt


def test_recall_skips_a_long_item_and_hot_text_stays_inside_its_budget() -> None:
    packed = pack_recall([(0.9, "甲" * 10), (0.5, "乙乙"), (0.1, "丙")], 4)
    assert "甲" not in packed
    assert "乙乙" in packed
    assert "丙" in packed
    assert len(packed) <= 4
    hot = pack_hot([("instruction", "指令"), ("identity", "身" * 50), ("boundary", "边界")], 12)
    assert len(hot) <= 12
    assert hot.startswith("身")
    huge = "身" * 2000
    messages = build_messages(
        identity_text=huge,
        hot_text=pack_hot([("identity", huge)], 800),
        thought=Thought(depth=1),
        recall_text="",
        buffer=Buffer(12),
        user_text="你好",
    )
    assert messages[0]["content"].startswith(huge)
    hot_body = messages[1]["content"].split("热层：\n", 1)[1]
    assert len(hot_body) <= 800
    assert len(huge) > 800
