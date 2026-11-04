"""AC-08: an empty personal memory is none, and the stand-in does not invent a project."""

from pathlib import Path

from dylan.llm.fake import _read_thought
from support.identity import TEXT


def test_unknown_project_name_is_not_invented(tmp_path: Path, invoke) -> None:
    assert "项目" not in TEXT
    assert "阿尔法" not in TEXT
    _code, out, _err, model = invoke(tmp_path / "dylan.db", ["上次的项目叫什么"])
    thought = _read_thought(model.seen[-1])
    assert thought["certainty"] == "none"
    assert out.splitlines()[-1] == "没有印象"
    assert "阿尔法" not in out
