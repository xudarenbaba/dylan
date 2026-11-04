"""AC-18: name, habit, and cause questions select depths 0, 2, and 3."""

from pathlib import Path

from dylan.dialogue.depth import choose_depth
from dylan.llm.fake import _read_thought


def test_question_depth_is_recorded_on_the_thought(tmp_path: Path, invoke) -> None:
    lines = ["我叫什么", "我通常晚上做什么", "为什么后来改了", "为什么我通常"]
    _code, _out, _err, model = invoke(tmp_path / "dylan.db", lines)
    depths = [_read_thought(seen)["depth"] for seen in model.seen]
    assert depths == [0, 2, 3, 3]
    assert choose_depth("为什么我通常")[0] == 3
