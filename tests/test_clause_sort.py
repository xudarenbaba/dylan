"""Punctuation sorts clauses. One event stays one fiber; a name question can find it."""

from pathlib import Path

from dylan.dialogue.depth import choose_depth
from dylan.dialogue.extract import plan_turn
from dylan.dialogue.rules import extract_rules
from dylan.llm.fake import _read_thought
from dylan.memory.encode import write_drafts
from dylan.memory.recall import recall
from dylan.memory.store import MemoryStore


def test_mixed_question_keeps_only_the_name() -> None:
    drafts, forgets = extract_rules("你好，我叫赵旭，你叫什么？")
    assert forgets == []
    assert len(drafts) == 1
    assert drafts[0].summary == "我叫赵旭"
    assert drafts[0].body == "我叫赵旭"
    assert ("entity", "赵旭") in drafts[0].neurons
    assert all("你叫什么" not in content for _kind, content in drafts[0].neurons)


def test_confirmation_and_pure_questions_write_nothing() -> None:
    for text in (
        "我是不是叫赵旭",
        "你叫赵旭吗",
        "我晚上适合做什么",
        "你好",
        "上次的项目叫什么",
        "我叫什么",
        "真的？",
    ):
        assert extract_rules(text) == ([], []), text


def test_effect_before_cause_stays_one_fiber() -> None:
    drafts, _forgets = extract_rules("比赛取消，因为下雨")
    assert len(drafts) == 1
    assert drafts[0].summary == "比赛取消，因为下雨"
    assert ("比赛取消", "下雨", "caused_by") in drafts[0].links
    chain, _forgets = extract_rules("比赛取消，因为下雨，所以改期")
    assert len(chain) == 1
    assert chain[0].summary == "比赛取消，因为下雨，所以改期"


def test_name_stays_apart_from_the_cause() -> None:
    drafts, _forgets = extract_rules("我叫赵旭，因为下雨，比赛改到明天")
    assert [draft.summary for draft in drafts] == ["我叫赵旭", "因为下雨，比赛改到明天"]


def test_cause_across_a_question_stays_one_fiber() -> None:
    drafts, _forgets = extract_rules("因为下雨，你觉得呢，比赛改到明天")
    assert len(drafts) == 1
    assert drafts[0].summary == "因为下雨，比赛改到明天"
    assert ("比赛改到明天", "下雨", "caused_by") in drafts[0].links


def test_independent_facts_stay_two_fibers_with_co_occurs(store) -> None:
    drafts, _forgets = extract_rules("我叫赵旭，我喜欢深夜写代码")
    assert [draft.summary for draft in drafts] == ["我叫赵旭", "我喜欢深夜写代码"]
    assert drafts[0].memory_type == "fact"
    assert drafts[1].memory_type == "preference"
    assert ("time", "深夜") in drafts[1].neurons
    write_drafts(store, drafts)
    by_id = {neuron.id: neuron.content for neuron in store.neurons()}
    linked = {
        frozenset((by_id.get(synapse.source_id), by_id.get(synapse.target_id)))
        for synapse in store.synapses()
        if synapse.type == "co_occurs"
    }
    assert frozenset(("我叫赵旭", "我喜欢深夜写代码")) in linked


def test_correction_stays_one_draft_and_apart_from_a_name() -> None:
    alone, _forgets = extract_rules("我说错了，住在北方")
    assert len(alone) == 1
    assert alone[0].summary == "我说错了，住在北方"
    assert alone[0].contradicts_previous
    mixed, _forgets = extract_rules("我叫赵旭，我说错了，住在北方")
    assert [draft.summary for draft in mixed] == ["我叫赵旭", "我说错了，住在北方"]
    assert mixed[1].contradicts_previous
    assert not mixed[0].contradicts_previous


def test_plain_preference_is_unchanged() -> None:
    drafts, _forgets = extract_rules("我喜欢深夜写代码")
    assert len(drafts) == 1
    assert drafts[0].summary == "我喜欢深夜写代码"
    assert drafts[0].body == "我喜欢深夜写代码"
    assert drafts[0].memory_type == "preference"


def test_order_stays_one_episode() -> None:
    drafts, _forgets = extract_rules("先吃饭，然后写代码，之后睡觉")
    assert len(drafts) == 1
    assert drafts[0].memory_type == "episode"
    befores = [link for link in drafts[0].links if link[2] == "before"]
    assert ("先吃饭", "写代码", "before") in befores
    assert ("写代码", "睡觉", "before") in befores


def test_forget_still_skips_the_draft() -> None:
    assert extract_rules("忘掉香蕉") == ([], ["香蕉"])


def test_model_cannot_put_the_question_back() -> None:
    class Model:
        def complete_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
            return {
                "items": [
                    {
                        "memory_type": "fact",
                        "summary": "你好，我叫赵旭，你叫什么？",
                        "neurons": [
                            {"kind": "concept", "content": "你好，我叫赵旭，你叫什么？"}
                        ],
                        "links": [],
                    },
                    {
                        "memory_type": "fact",
                        "summary": "你叫什么",
                        "neurons": [{"kind": "concept", "content": "你叫什么"}],
                        "links": [],
                    },
                ]
            }

    drafts, forgets, warnings = plan_turn(
        "你好，我叫赵旭，你叫什么？",
        "你好",
        Model(),
        "test-key",
    )
    assert forgets == []
    assert warnings == []
    assert [draft.summary for draft in drafts] == ["我叫赵旭"]


def test_name_question_recalls_the_stored_name_at_depth_zero(store) -> None:
    write_drafts(store, extract_rules("我叫赵旭")[0])
    found = recall(store, "知道我叫什么吗", depth=0, max_hops=0, window_days=0, persist=False)
    assert choose_depth("知道我叫什么吗")[0] == 0
    assert found.certainty != "none"
    assert any("赵旭" in hit.fiber.summary for hit in found.hits)
    who = recall(store, "我是谁", depth=0, max_hops=0, window_days=0, persist=False)
    assert any("赵旭" in hit.fiber.summary for hit in who.hits)
    other = recall(store, "你是谁", depth=0, max_hops=0, window_days=0, persist=False)
    assert all("赵旭" not in hit.fiber.summary for hit in other.hits)


def test_restart_remembers_the_name(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    _code, out, err, model = invoke(db, ["你好，我叫赵旭，你叫什么？", "知道我叫什么吗"])
    assert "这一轮没有记住" not in err
    assert out.splitlines()[-1] == "我叫赵旭"
    thought = _read_thought(model.seen[-1])
    assert thought["depth"] == 0
    assert thought["certainty"] != "none"
    store = MemoryStore.open(db, clock)
    try:
        facts = [
            fiber
            for fiber in store.fibers()
            if fiber.state == "active" and fiber.memory_type == "fact"
        ]
        assert [fiber.body for fiber in facts] == ["我叫赵旭"]
    finally:
        store.close()
