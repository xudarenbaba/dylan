"""AC-11: a broken stream keeps the partial text and does not store the turn."""

from pathlib import Path

from dylan.config import Settings
from dylan.errors import AuthFailed, NetworkError, ServiceError, TimeoutError_
from dylan.llm.client import map_error
from dylan.llm.fake import FakeModel
from dylan.memory.store import MemoryStore


def test_interrupted_stream_is_visible_and_not_stored(tmp_path: Path, clock, invoke) -> None:
    db = tmp_path / "dylan.db"
    model = FakeModel()
    model.partial = "ZZPARTIAL"
    model.fail = NetworkError()
    code, out, err, _model = invoke(db, ["请记住甲组的暗号"], model=model)
    assert code == 0
    assert "ZZPARTIAL" in out
    assert "网络中断" in err
    store = MemoryStore.open(db, clock)
    try:
        assert not store.search_text("ZZPARTIAL")
        assert not store.search_text("请记住甲组的暗号")
        assert not any(fiber.auto_session for fiber in store.fibers())
    finally:
        store.close()


def test_map_error_uses_the_class_name_and_timeout_defaults_to_60() -> None:
    class ReadTimeout(Exception):
        def __str__(self) -> str:
            return "sk-abcdefghijklmnopqrst"

    class AuthenticationError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class APIStatusError(Exception):
        pass

    mapped = map_error(ReadTimeout())
    assert isinstance(mapped, TimeoutError_)
    assert mapped.category == "超时"
    assert "sk-" not in str(mapped)
    assert map_error(AuthenticationError()).category == "认证失败"
    assert isinstance(map_error(AuthenticationError()), AuthFailed)
    assert map_error(RateLimitError()).category == "服务错误"
    assert isinstance(map_error(APIStatusError()), ServiceError)
    assert map_error(ConnectionError("down")).category == "网络中断"
    assert Settings().dylan_timeout_seconds == 60
