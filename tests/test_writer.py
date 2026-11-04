"""The writer checks her proposals: sources, targets, types, plans, secrets, the journal."""

from __future__ import annotations

from conftest import fact


def _user_fibers(store):
    return [fiber for fiber in store.fibers() if fiber.memory_type != "innate"]


def test_add_builds_nodes_aliases_relations_and_cues(store, note) -> None:
    note(
        [
            fact(
                "赵旭养了一只猫，叫团子",
                "我养了一只猫叫团子",
                nodes=[{"name": "团子", "kind": "animal", "aliases": ["猫咪"]}],
                relations=[{"source": "赵旭", "type": "raises", "target": "团子"}],
                cues=["团子", "宠物"],
            )
        ],
        user_text="我养了一只猫叫团子",
    )
    fiber = _user_fibers(store)[0]
    assert fiber.source == "user"
    assert fiber.detail == "我养了一只猫叫团子"
    pet = store.find_nodes("猫咪")
    assert pet and pet[0].name == "团子" and pet[0].kind == "animal"
    user_id = store.meta()["user_id"]
    assert store.synapse_between(user_id, pet[0].id, "raises") is not None
    assert set(fiber.cues) == {"团子", "宠物"}


def test_claimed_quote_that_he_never_said_becomes_inference(store, note) -> None:
    outcome = note(
        [fact("赵旭讨厌香菜", "我讨厌香菜")],
        user_text="今天随便吃了点",
    )
    fiber = _user_fibers(store)[0]
    assert fiber.source == "inference"
    assert fiber.confidence is not None
    assert "原话对不上" in outcome.lines[0]


def test_what_she_said_about_him_is_only_her_inference(store, note) -> None:
    note(
        [
            {
                "op": "add",
                "type": "impression",
                "about": "赵旭",
                "statement": "赵旭最近压力很大",
                "evidence": "你最近压力好大",
                "source": "self",
            },
            {
                "op": "add",
                "type": "self",
                "about": "dylan",
                "statement": "dylan 发现自己很喜欢听他讲游戏",
                "evidence": "我好喜欢听你讲游戏",
                "source": "self",
            },
        ],
        user_text="嗯",
        reply_text="你最近压力好大呀。我好喜欢听你讲游戏！",
    )
    by_type = {fiber.memory_type: fiber for fiber in _user_fibers(store)}
    assert by_type["impression"].source == "inference"
    assert by_type["self"].source == "self"


def test_unknown_targets_types_and_sleep_only_types_are_rejected(store, note) -> None:
    outcome = note(
        [
            {"op": "reinforce", "target": "m9"},
            {"op": "add", "type": "error", "statement": "报错了"},
            {"op": "add", "type": "session", "statement": "我们聊了天", "source": "shared"},
            {"op": "merge", "keep": "m1", "drop": ["m2"]},
            {"op": "add", "type": "plan", "statement": "赵旭要去面试", "source": "inference"},
        ]
    )
    assert outcome.rejected == 5
    assert _user_fibers(store) == []
    notes = [row for row in store.journal() if row["phase"] == "note"]
    assert len(notes) == 5 and all(row["status"] == "rejected" for row in notes)


def test_a_plan_needs_a_time_or_a_trigger(store, note) -> None:
    note(
        [
            {
                "op": "add",
                "type": "plan",
                "statement": "赵旭明天下午三点面试",
                "evidence": "明天下午三点面试",
                "source": "user",
                "due": "2026-11-04 15:00",
            }
        ],
        user_text="我明天下午三点面试",
    )
    plan = _user_fibers(store)[0]
    assert plan.due_at == "2026-11-04T07:00:00Z"


def test_secrets_are_never_stored_anywhere(store, note) -> None:
    token = "sk-" + "a1b2c3d4e5f6g7h8i9j0"
    outcome = note(
        [
            fact("赵旭配置了接口", "配置了接口", cues=[token]),
            fact(
                "赵旭有一个账号",
                "有一个账号",
                relations=[{"source": "赵旭", "type": "owns", "target": token}],
            ),
            fact(f"赵旭的密钥是{token}", token),
        ],
        user_text=f"我配置了接口，有一个账号，{token}",
    )
    assert outcome.rejected == 3
    assert not store.search_text(token)


def test_suppress_needs_a_shown_memory_and_leaves_a_trace(store, note) -> None:
    note([fact("赵旭的前任叫小美", "我前任叫小美")], user_text="我前任叫小美")
    ex = _user_fibers(store)[0]
    note([{"op": "suppress", "target": "m1"}], user_text="忘掉我前任的事吧", shown=[ex])
    assert store.fiber(ex.id).state == "suppressed"
    trace = [fiber for fiber in _user_fibers(store) if "忘掉了一件事" in fiber.statement]
    assert len(trace) == 1 and "小美" not in trace[0].statement


def test_journal_records_every_proposal(store, note) -> None:
    note(
        [fact("赵旭讨厌香菜", "我讨厌香菜"), {"op": "reinforce", "target": "m5"}],
        user_text="我讨厌香菜",
    )
    statuses = [row["status"] for row in store.journal() if row["phase"] == "note"]
    assert statuses.count("accepted") == 1
    assert statuses.count("rejected") == 1
