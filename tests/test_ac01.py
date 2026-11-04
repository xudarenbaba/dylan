"""AC-01: chat without a key exits before any database file exists."""

from pathlib import Path


def test_missing_key_exits_before_creating_a_database(tmp_path: Path, invoke) -> None:
    db = tmp_path / "nested" / "dylan.db"
    code, out, err, _model = invoke(db, ["你好"], key="")
    assert code != 0
    assert "DEEPSEEK_API_KEY" in err
    assert out == ""
    assert not db.exists()
    assert not db.parent.exists()
