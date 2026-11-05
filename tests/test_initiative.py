"""She decides whether to speak. Declining writes nothing."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from conftest import LETTER, TZ
from dylan.config import Settings
from dylan.desk.session import DeskClosed
from dylan.dialogue.loop import Conversation
from dylan.errors import NetworkError
from dylan.llm.fake import FakeModel
from dylan.memory.constants import (
    HER_TURN,
    INITIATIVE_IDLE_MAX_MINUTES,
    INITIATIVE_IDLE_MIN_MINUTES,
    INITIATIVE_LINE_CHARS,
    SCHEMA_VERSION,
)
from dylan.memory.life import Handles, birth
from dylan.memory.ops import Context, Writer
from dylan.memory.store import MemoryStore

_SAY = {"speak": True, "reason": "m1", "line": "面试怎么样了"}
_MISS = {"speak": True, "reason": "interval", "line": "有点想你了"}
_QUIET = {"speak": False, "line": ""}
_EMPTY_NOTE = {"ops": [], "used": [], "mood": None, "summary": ""}
_HEARD = "我明天下午三点面试"


def _talk(store, clock, model, show: bool = False):
    settings = Settings(deepseek_api_key="test-key", dylan_show_mind=show)
    return Conversation(store, settings, model, clock), StringIO(), StringIO()


def _plant(note, store, **extra):
    statement = extra.pop("statement", "问问赵旭面试怎么样")
    op: dict[str, object] = {
        "op": "add",
        "type": "plan",
        "about": "赵旭",
        "statement": statement,
        "evidence": _HEARD,
        "source": "user",
    }
    if "due" not in extra and "trigger" not in extra:
        op["trigger"] = "下次见面"
    op.update(extra)
    note([op], user_text=_HEARD)
    return [fiber for fiber in store.fibers() if fiber.memory_type == "plan"][-1]


def _blob(messages: list[dict[str, str]]) -> str:
    return "\n".join(message.get("content", "") for message in messages)


def _speaks(store) -> list:
    return [row for row in store.initiative_rows() if row["op"] == "speak"]


def test_schema_stays_at_two() -> None:
    assert SCHEMA_VERSION == 2


def test_the_gap_is_one_to_ten_minutes() -> None:
    assert INITIATIVE_IDLE_MIN_MINUTES == 1
    assert INITIATIVE_IDLE_MAX_MINUTES == 10
    assert INITIATIVE_LINE_CHARS == 120


def test_declining_writes_nothing(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_QUIET]
    before = len(store.fibers())
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is False
    talk.finish(err)
    assert len(model.calls("initiative")) == 1
    assert model.calls("sleep") == []
    assert model.seen == []
    assert out.getvalue() == ""
    assert "她决定先等" in err.getvalue()
    assert store.sessions() == []
    assert store.initiative_rows() == []
    assert len(store.fibers()) == before


def test_she_may_speak_with_no_plan(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_MISS]
    talk, out, _err = _talk(store, clock, model)
    assert talk.consider(out, _err, lambda: False) is True
    assert out.getvalue().strip() == "有点想你了"
    spoken = _speaks(store)
    assert len(spoken) == 1
    assert spoken[0]["reason"] == ""
    assert spoken[0]["fiber_id"] is None
    sent = _blob(model.calls("initiative")[0])
    assert "你还没有先开口过" in sent
    assert "可以先说的事" not in sent
    assert "分开已经比较久" not in sent
    assert "记忆类型：" not in sent


def test_a_plan_is_context_and_her_line_is_not_his_words(store, note, clock) -> None:
    plan = _plant(note, store)
    before = plan.strength
    model = FakeModel()
    model.initiatives = [_SAY]
    model.notes = [_EMPTY_NOTE]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is True
    sent = _blob(model.calls("initiative")[0])
    assert "问问赵旭面试怎么样" in sent
    assert "我是赵旭" in sent
    assert "〔先开口〕" in sent
    assert "记忆类型：" not in sent
    assert "此刻想起的事" not in sent
    assert "可以先说的事" not in sent
    assert "m1 或 interval" not in sent
    assert out.getvalue().strip() == "面试怎么样了"
    assert HER_TURN not in out.getvalue()
    assert "〔先说〕" in err.getvalue()
    assert "〔先说〕plan" not in err.getvalue()
    spoken = _speaks(store)
    assert len(spoken) == 1
    assert spoken[0]["reason"] == ""
    assert spoken[0]["fiber_id"] is None
    assert spoken[0]["fiber_id"] != plan.id
    assert talk.consider(out, err, lambda: False) is False
    again = _blob(model.calls("initiative")[1])
    assert "他还没接" in again
    assert "她决定先等" in err.getvalue()
    noted = _blob(model.calls("note")[0])
    assert "这一轮是你先开口，他没有说话" in noted
    assert "他：〔她先说〕" not in noted
    assert HER_TURN not in noted
    asked = [
        fiber
        for fiber in store.fibers()
        if fiber.memory_type != "innate" and fiber.statement == "面试怎么样了"
    ]
    assert asked == []
    assert store.fiber(plan.id).strength == before
    talk.turn("还行", out, err)
    history = model.seen[-1]
    assert any(
        item["role"] == "assistant" and item["content"] == "面试怎么样了" for item in history
    )
    assert all(HER_TURN not in item["content"] for item in history if item["role"] == "user")
    assert history[-1] == {"role": "user", "content": "还行"}
    talk.finish(err)
    slept = _blob(model.calls("sleep")[0])
    assert "她：面试怎么样了" in slept
    assert "他：〔她先说〕" not in slept
    assert store.counts()["turns"] == 0
    assert _speaks(store)


def test_her_line_is_not_stored_as_something_he_said(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY]
    model.notes = [
        {
            "ops": [
                {
                    "op": "add",
                    "type": "fact",
                    "about": "赵旭",
                    "statement": "赵旭说面试怎么样了",
                    "evidence": "面试怎么样了",
                    "source": "user",
                },
                {
                    "op": "add",
                    "type": "fact",
                    "about": "赵旭",
                    "statement": "赵旭先开口了",
                    "evidence": HER_TURN,
                    "source": "user",
                },
            ],
            "used": [],
            "mood": None,
            "summary": "",
        }
    ]
    talk, out, err = _talk(store, clock, model)
    assert talk.consider(out, err, lambda: False) is True
    assert talk.consider(out, err, lambda: False) is False
    assert len(model.calls("initiative")) == 2
    quoted = [fiber for fiber in store.fibers() if fiber.statement == "赵旭说面试怎么样了"]
    assert len(quoted) == 1 and quoted[0].source == "inference"
    sentinel = [fiber for fiber in store.fibers() if fiber.statement == "赵旭先开口了"]
    assert sentinel and all(fiber.source != "user" for fiber in sentinel)


def test_an_unanswered_line_is_a_fact_and_she_may_speak_again(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY, _SAY]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is True
    talk.finish(err)
    clock.advance(hours=2)
    again, out2, err2 = _talk(store, clock, model, show=True)
    assert again.consider(out2, err2, lambda: False) is True
    assert len(model.calls("initiative")) == 2
    assert "他还没接" in _blob(model.calls("initiative")[1])
    assert "上一句他还没回" not in err2.getvalue()
    assert out2.getvalue().strip() == "面试怎么样了"
    assert store.initiative_rows()[-1]["op"] == "speak"


def test_after_he_answers_she_is_told(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY, _QUIET]
    model.notes = [_EMPTY_NOTE]
    talk, out, err = _talk(store, clock, model)
    assert talk.consider(out, err, lambda: False) is True
    talk.turn("还行", out, err)
    assert store.initiative_rows()[-1]["op"] == "heard"
    assert talk.consider(out, err, lambda: False) is False
    sent = _blob(model.calls("initiative")[-1])
    assert "他已经接过了" in sent
    assert "他还没接" not in sent
    assert "他：还行" in sent


@pytest.mark.parametrize(
    "proposal",
    [
        {"speak": "true", "line": "面试怎么样了"},
        {"speak": 1, "line": "面试怎么样了"},
        {"speak": True, "line": ""},
        {"speak": True, "line": "   "},
        {"speak": True, "line": "〔面试怎么样了〕"},
        {"speak": True, "line": "面试怎么样了〕"},
        {"speak": True, "line": None},
    ],
)
def test_a_bad_line_is_not_stored(store, clock, proposal) -> None:
    model = FakeModel()
    model.initiatives = [proposal]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is False
    assert len(model.calls("initiative")) == 1
    assert out.getvalue() == ""
    assert store.sessions() == []
    assert store.initiative_rows() == []
    assert "这句不能说" in err.getvalue()


def test_a_line_may_mention_a_handle(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [{"speak": True, "line": "m1 面试怎么样了"}]
    talk, out, _err = _talk(store, clock, model)
    assert talk.consider(out, _err, lambda: False) is True
    assert out.getvalue().strip() == "m1 面试怎么样了"


def test_a_long_line_is_clipped(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [{"speak": True, "line": "想" * 121}]
    talk, out, _err = _talk(store, clock, model)
    assert talk.consider(out, _err, lambda: False) is True
    assert out.getvalue().strip() == "想" * 120
    assert _speaks(store)[0]["label"] == "想" * 80


def test_a_secret_line_is_dropped(store, clock) -> None:
    token = "sk-" + "b" * 20
    model = FakeModel()
    model.initiatives = [{"speak": True, "line": f"看下{token}"}]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is False
    assert token not in out.getvalue()
    assert token not in err.getvalue()
    assert "这句不能说" in err.getvalue()
    assert store.sessions() == []
    assert store.initiative_rows() == []


def test_a_failed_decision_stays_quiet(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [RuntimeError("nope")]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is False
    assert "这次没有想好" in err.getvalue()
    assert "网络中断" not in err.getvalue()
    assert "网络中断" not in out.getvalue()
    assert store.sessions() == []


def test_night_a_fresh_reply_and_repetition_do_not_block_her(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY, _SAY, _SAY]
    talk, out, err = _talk(store, clock, model, show=True)
    clock.advance(hours=3.5)
    assert talk.consider(out, err, lambda: False) is True
    assert talk.consider(out, err, lambda: False) is True
    talk.turn("我先说一句", out, err)
    assert talk.consider(out, err, lambda: False) is True
    assert len(model.calls("initiative")) == 3
    text = err.getvalue()
    assert "夜里不打扰" not in text
    assert "今天已经说过了" not in text
    assert "隔得太近" not in text
    assert "他刚说过话" not in text
    assert len(_speaks(store)) == 3


def test_his_reply_is_heard_even_when_the_answer_fails(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY, _SAY]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: False) is True
    model.partial = "半"
    model.fail = NetworkError()
    talk.turn("我在", out, err)
    assert store.initiative_rows()[-1]["op"] == "heard"
    model.fail = None
    model.partial = None
    assert talk.consider(out, err, lambda: False) is True
    assert len(model.calls("initiative")) == 2


def test_ordinary_turns_do_not_fill_the_ledger(store, clock) -> None:
    model = FakeModel()
    talk, out, err = _talk(store, clock, model)
    talk.turn("你好", out, err)
    talk.turn("在吗", out, err)
    assert store.initiative_rows() == []


def test_cancelled_before_the_model_does_not_call_it(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY]
    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, lambda: True) is False
    assert model.calls("initiative") == []
    assert "他正在说话" in err.getvalue()
    assert store.sessions() == []


def test_cancelled_after_the_model_discards_the_line(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY]
    seen = {"n": 0}

    def cancelled() -> bool:
        seen["n"] += 1
        return seen["n"] > 1

    talk, out, err = _talk(store, clock, model, show=True)
    assert talk.consider(out, err, cancelled) is False
    assert len(model.calls("initiative")) == 1
    assert out.getvalue() == ""
    assert store.sessions() == []
    assert "他正在说话" in err.getvalue()


def test_closing_during_the_write_does_not_store(store, clock) -> None:
    model = FakeModel()
    model.initiatives = [_SAY]
    talk, _out, err = _talk(store, clock, model, show=True)

    class _Cut:
        def write(self, _text: str) -> int:
            raise DeskClosed()

        def flush(self) -> None:
            return None

    with pytest.raises(DeskClosed):
        talk.consider(_Cut(), err, lambda: False)
    assert "〔先说〕" not in err.getvalue()
    assert store.sessions() == []
    assert store.initiative_rows() == []


def test_the_command_line_waits_for_him(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    _born_plan(db, clock)
    model = FakeModel()
    model.initiatives = [_SAY]
    code, out, _err, model = invoke(db, ["你好", "exit"], model=model)
    assert code == 0
    assert model.calls("initiative") == []
    assert "面试怎么样了" not in out


def _born_plan(db: Path, clock) -> None:
    store = MemoryStore.create(db, clock)
    try:
        birth(store, LETTER, FakeModel().default_birth(LETTER), TZ)
        handles = Handles()
        ctx = Context(
            phase="note",
            tz=TZ,
            api_key="",
            user_text=_HEARD,
            reply_text="",
            handles=dict(handles.by_handle),
        )
        with store.transaction():
            Writer(store, ctx).apply(
                [
                    {
                        "op": "add",
                        "type": "plan",
                        "about": "赵旭",
                        "statement": "问问赵旭面试怎么样",
                        "evidence": _HEARD,
                        "source": "user",
                        "trigger": "下次见面",
                    }
                ]
            )
    finally:
        store.close()
