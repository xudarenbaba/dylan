"""How memories change: reinforce, update, supersede, contradict, complete, merge."""

from __future__ import annotations

from conftest import TZ, fact
from dylan.memory.physiology import clarity
from dylan.memory.recall import recall


def _active(store, text: str):
    return next(fiber for fiber in store.fibers() if fiber.statement == text)


def test_reinforce_strengthens_without_a_second_copy(store, note, clock) -> None:
    note([fact("赵旭讨厌香菜", "我讨厌香菜")], user_text="我讨厌香菜")
    first = _active(store, "赵旭讨厌香菜")
    clock.advance(days=4)
    note([{"op": "reinforce", "target": "m1"}], user_text="香菜真的好难吃", shown=[first])
    again = _active(store, "赵旭讨厌香菜")
    assert again.recall_count == 1
    assert again.strength > first.strength - 0.05
    assert sum(1 for fiber in store.fibers() if "香菜" in fiber.statement) == 1


def test_supersede_keeps_the_old_one_as_the_past(store, note) -> None:
    note(
        [fact("赵旭住在杭州", "我住在杭州", nodes=[{"name": "杭州", "kind": "place"}])],
        user_text="我住在杭州",
    )
    old = _active(store, "赵旭住在杭州")
    note(
        [
            {
                "op": "supersede",
                "target": "m1",
                "with": fact(
                    "赵旭搬到了上海",
                    "我搬到上海了",
                    nodes=[{"name": "上海", "kind": "place"}],
                ),
            }
        ],
        user_text="我搬到上海了",
        shown=[old],
    )
    past = store.fiber(old.id)
    assert past.state == "superseded" and past.valid_until is not None
    assert clarity(past) == "past"
    found = recall(store, ["我以前住哪来着，杭州还是上海"], TZ)
    clarities = {hit.fiber.statement: hit.clarity for hit in found.hits}
    assert clarities.get("赵旭搬到了上海") == "clear"
    assert clarities.get("赵旭住在杭州") == "past"


def test_contradiction_brings_both_sides_to_mind(store, note) -> None:
    note([fact("赵旭的生日是3月12日", "我生日3月12日", cues=["生日"])], user_text="我生日3月12日")
    first = _active(store, "赵旭的生日是3月12日")
    note(
        [
            {
                "op": "contradict",
                "target": "m1",
                "with": fact("赵旭的生日是3月21日", "我生日是3月21日", cues=["生日"]),
            }
        ],
        user_text="我生日是3月21日",
        shown=[first],
    )
    found = recall(store, ["我生日是哪天"], TZ)
    seen = {hit.fiber.statement: hit.clarity for hit in found.hits}
    assert seen == {"赵旭的生日是3月12日": "conflict", "赵旭的生日是3月21日": "conflict"}


def test_completing_a_plan_writes_what_happened(store, note) -> None:
    note(
        [
            {
                "op": "add",
                "type": "plan",
                "statement": "赵旭明天面试",
                "evidence": "明天面试",
                "source": "user",
                "due": "2026-11-04 15:00",
                "cues": ["面试"],
            }
        ],
        user_text="我明天面试",
    )
    plan = _active(store, "赵旭明天面试")
    note(
        [
            {
                "op": "complete",
                "target": "m1",
                "with": {
                    "type": "event",
                    "statement": "赵旭面试通过了",
                    "evidence": "面试过了",
                    "source": "user",
                    "occurred": "2026-11-04",
                },
            }
        ],
        user_text="面试过了！",
        shown=[plan],
    )
    assert store.fiber(plan.id).state == "done"
    event = _active(store, "赵旭面试通过了")
    assert event.memory_type == "event" and event.occurred_start == "2026-11-03T16:00:00Z"


def test_update_keeps_the_same_memory(store, note) -> None:
    note([fact("赵旭养了一只猫", "我养了一只猫")], user_text="我养了一只猫")
    cat = _active(store, "赵旭养了一只猫")
    note(
        [
            {
                "op": "update",
                "target": "m1",
                "statement": "赵旭养了一只橘猫，叫团子",
                "evidence": "是只橘猫，叫团子",
                "nodes": [{"name": "团子", "kind": "animal"}],
            }
        ],
        user_text="是只橘猫，叫团子",
        shown=[cat],
    )
    again = store.fiber(cat.id)
    assert again.statement == "赵旭养了一只橘猫，叫团子"
    assert store.find_nodes("团子")
    assert sum(1 for fiber in store.fibers() if "猫" in fiber.statement) == 1


def test_sleep_merge_folds_duplicates_into_one(store, note) -> None:
    note([fact("赵旭喜欢深夜写代码", "我喜欢深夜写代码")], user_text="我喜欢深夜写代码")
    note([fact("赵旭习惯晚上写代码", "我晚上写代码")], user_text="我晚上写代码")
    left = _active(store, "赵旭喜欢深夜写代码")
    right = _active(store, "赵旭习惯晚上写代码")
    note(
        [
            {
                "op": "merge",
                "keep": "m1",
                "drop": ["m2"],
                "statement": "赵旭喜欢在深夜写代码",
                "cues": ["深夜", "晚上", "写代码"],
            }
        ],
        shown=[left, right],
        phase="sleep",
    )
    kept = store.fiber(left.id)
    assert kept.statement == "赵旭喜欢在深夜写代码"
    assert store.fiber(right.id).state == "merged"
    assert {"深夜", "晚上"} <= set(kept.cues)
