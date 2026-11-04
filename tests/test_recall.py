"""Recall by names, aliases, cues and dates; spreading; awareness; co-recall growth."""

from __future__ import annotations

from conftest import TZ, fact
from dylan.memory.awareness import build_awareness
from dylan.memory.recall import persist_recall, recall


def _statements(found) -> list[str]:
    return [hit.fiber.statement for hit in found.hits]


def _pet(store, note) -> None:
    note(
        [
            fact(
                "赵旭养了一只猫，叫团子",
                "我养了一只猫叫团子",
                nodes=[{"name": "团子", "kind": "animal", "aliases": ["猫", "猫咪"]}],
                cues=["宠物"],
            )
        ],
        user_text="我养了一只猫叫团子",
    )


def test_a_name_or_an_alias_brings_the_memory_back(store, note) -> None:
    _pet(store, note)
    assert "赵旭养了一只猫，叫团子" in _statements(recall(store, ["团子最近怎么样"], TZ))
    assert "赵旭养了一只猫，叫团子" in _statements(recall(store, ["我的猫叫什么"], TZ))
    assert "赵旭养了一只猫，叫团子" in _statements(recall(store, ["你喜欢宠物吗"], TZ))


def test_nothing_comes_to_mind_for_unrelated_words(store, note) -> None:
    _pet(store, note)
    assert recall(store, ["今天天气怎么样"], TZ).hits == []


def test_he_and_she_do_not_relay_activation(store, note) -> None:
    _pet(store, note)
    note([fact("赵旭讨厌香菜", "我讨厌香菜")], user_text="我讨厌香菜")
    found = recall(store, ["赵旭"], TZ)
    assert found.hits == []


def test_spreading_reaches_a_memory_through_a_shared_node(store, note) -> None:
    _pet(store, note)
    note(
        [
            {
                "op": "add",
                "type": "event",
                "statement": "团子今天生病了，赵旭很担心",
                "evidence": "团子今天生病了",
                "source": "user",
                "nodes": [{"name": "团子", "kind": "animal"}],
                "occurred": "2026-11-03",
            }
        ],
        user_text="团子今天生病了",
    )
    found = recall(store, ["我的猫咪"], TZ)
    assert "团子今天生病了，赵旭很担心" in _statements(found)


def test_a_date_brings_back_what_happened_that_day(store, note) -> None:
    note(
        [
            {
                "op": "add",
                "type": "event",
                "statement": "赵旭去医院复查",
                "evidence": "去医院复查",
                "source": "user",
                "occurred": "2026-11-03",
            }
        ],
        user_text="我今天去医院复查",
    )
    assert "赵旭去医院复查" in _statements(recall(store, ["今天发生了什么"], TZ))
    assert "赵旭去医院复查" in _statements(recall(store, ["11月3日我干嘛了"], TZ))


def test_awareness_holds_what_matters_and_recall_does_not_repeat_it(store, note) -> None:
    note(
        [
            fact("赵旭不想被叫宝贝", "别叫我宝贝", type="agreement", importance=8),
            {
                "op": "add",
                "type": "plan",
                "statement": "赵旭明天下午三点面试",
                "evidence": "明天下午三点面试",
                "source": "user",
                "due": "2026-11-04 15:00",
            },
        ],
        user_text="别叫我宝贝，我明天下午三点面试",
    )
    aware = build_awareness(store, TZ)
    assert "赵旭不想被叫宝贝" in aware.text
    assert "心里惦记的事" in aware.text and "面试" in aware.text
    assert "现在是 2026-11-03 20:00 星期二" in aware.text
    assert "这是你第一次和赵旭聊天" in aware.text
    found = recall(store, ["别叫我宝贝"], TZ, exclude=set(aware.fiber_ids))
    assert "赵旭不想被叫宝贝" not in _statements(found)


def test_awareness_respects_its_budget(store, note) -> None:
    ops = [
        fact(f"赵旭喜欢第{index}种水果", f"喜欢第{index}种水果", type="preference")
        for index in range(8)
    ]
    note(ops, user_text="".join(f"喜欢第{index}种水果" for index in range(8)))
    aware = build_awareness(store, TZ, budget=300)
    assert len(aware.text) <= 300


def test_recalling_together_grows_a_link(store, note) -> None:
    _pet(store, note)
    note([fact("赵旭给团子买了猫粮", "给团子买了猫粮", cues=["团子"])], user_text="给团子买了猫粮")
    for _round in range(2):
        found = recall(store, ["团子"], TZ)
        with store.transaction():
            persist_recall(store, found, TZ)
    assert any(synapse.type == "co_recalled" for synapse in store.synapses())
