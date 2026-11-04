"""Physiology: encoding, forgetting by type, fading detail, settling, clarity, mood."""

from __future__ import annotations

from conftest import TZ, fact
from dylan.memory.maintain import maintain
from dylan.memory.model import Mood
from dylan.memory.physiology import clarity, current_mood, strengthen


def _one(store, text: str):
    return next(fiber for fiber in store.fibers() if fiber.statement == text)


def _by_id(store, fiber_id: str):
    return store.fiber(fiber_id)


def test_a_fresh_memory_is_clear(store, note) -> None:
    note([fact("赵旭讨厌香菜", "我讨厌香菜")], user_text="我讨厌香菜")
    fiber = _one(store, "赵旭讨厌香菜")
    assert fiber.strength >= 0.8
    assert clarity(fiber) == "clear"


def test_strong_feelings_and_importance_are_remembered_longer(store, note, clock) -> None:
    note(
        [
            fact("赵旭今天吃了面", "我今天吃了面", importance=2, type="event"),
            fact(
                "赵旭今天被裁员了",
                "我今天被裁员了",
                importance=9,
                type="event",
                emotion={"who": "赵旭", "label": "难过", "intensity": 0.9},
            ),
        ],
        user_text="我今天吃了面。我今天被裁员了",
    )
    lunch_id = _one(store, "赵旭今天吃了面").id
    layoff_id = _one(store, "赵旭今天被裁员了").id
    clock.advance(days=40)
    maintain(store)
    lunch = _by_id(store, lunch_id)
    layoff = _by_id(store, layoff_id)
    assert layoff.strength > lunch.strength
    assert clarity(layoff) == "clear"
    assert clarity(lunch) in {"vague", "trace"}


def test_status_fades_in_days_while_agreements_last(store, note, clock) -> None:
    note(
        [
            fact("赵旭这周在加班", "我这周在加班", type="status"),
            fact("赵旭不想被叫宝贝", "别叫我宝贝", type="agreement"),
        ],
        user_text="我这周在加班，别叫我宝贝",
    )
    agreement = _one(store, "赵旭不想被叫宝贝")
    status_id = _one(store, "赵旭这周在加班").id
    clock.advance(days=30)
    maintain(store)
    assert _by_id(store, agreement.id).strength > 0.9 * agreement.strength
    assert _by_id(store, status_id).strength < 0.3


def test_detail_fades_first_and_never_comes_back(store, note, clock) -> None:
    said = "我小时候在海边长大"
    note([fact("赵旭小时候在海边长大", said, type="event")], user_text=said)
    clock.advance(days=120)
    maintain(store)
    fiber = next(item for item in store.fibers() if item.memory_type == "event")
    assert fiber.detail_level >= 2
    assert fiber.detail == "" and fiber.evidence == ""
    again = strengthen(fiber, clock.now(), 0.5, TZ, count=True)
    assert again.detail == ""
    assert again.detail_level >= 1


def test_settling_twice_at_the_same_time_changes_nothing(store, note, clock) -> None:
    note([fact("赵旭讨厌香菜", "我讨厌香菜")], user_text="我讨厌香菜")
    clock.advance(days=10)
    maintain(store)
    first = _one(store, "赵旭讨厌香菜")
    maintain(store)
    assert _one(store, "赵旭讨厌香菜").strength == first.strength


def test_spaced_recall_settles_a_memory(store, note, clock) -> None:
    note([fact("赵旭讨厌香菜", "我讨厌香菜")], user_text="我讨厌香菜")
    fiber = _one(store, "赵旭讨厌香菜")
    for _day in range(6):
        clock.advance(days=2)
        fiber = strengthen(fiber, clock.now(), 0.08, TZ, count=True)
    assert fiber.stage == "settled"
    with store.transaction():
        store.save_fiber(fiber)
    clock.advance(days=200)
    maintain(store)
    assert _one(store, "赵旭讨厌香菜").strength >= 0.6


def test_innate_memories_never_fade(store, clock) -> None:
    clock.advance(days=3650)
    maintain(store)
    innate = [fiber for fiber in store.fibers() if fiber.memory_type == "innate"]
    assert innate and all(fiber.strength == 1.0 for fiber in innate)


def test_inference_is_a_feeling_or_a_guess(store, note) -> None:
    note(
        [
            {
                "op": "add",
                "type": "impression",
                "statement": "赵旭压力大时话会变少",
                "source": "inference",
                "confidence": 0.6,
            },
            {
                "op": "add",
                "type": "impression",
                "statement": "赵旭可能不喜欢热闹",
                "source": "inference",
                "confidence": 0.3,
            },
        ]
    )
    assert clarity(_one(store, "赵旭压力大时话会变少")) == "feeling"
    assert clarity(_one(store, "赵旭可能不喜欢热闹")) == "guess"


def test_mood_returns_to_baseline(clock) -> None:
    mood = Mood(label="委屈", intensity=0.8, cause="他没回消息", at="2026-11-03T12:00:00Z")
    clock.advance(hours=2)
    assert current_mood(mood, clock.now()) is not None
    clock.advance(hours=24)
    assert current_mood(mood, clock.now()) is None


def test_suppressed_memories_fade_and_are_eventually_gone(store, note, clock) -> None:
    note([fact("赵旭的前任叫小美", "我前任叫小美")], user_text="我前任叫小美")
    ex = _one(store, "赵旭的前任叫小美")
    note([{"op": "suppress", "target": "m1"}], user_text="忘了她吧", shown=[ex])
    clock.advance(days=4)
    maintain(store)
    faded = store.fiber(ex.id)
    assert faded.detail == "" and faded.strength < 0.2
    clock.advance(days=30)
    maintain(store)
    assert store.fiber(ex.id) is None
    assert not store.search_text("小美")
