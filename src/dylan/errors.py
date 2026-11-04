"""Error categories. Messages never include secrets or request headers."""

from __future__ import annotations


class DylanError(Exception):
    category = "写入失败"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        super().__init__(self.category if not detail else f"{self.category}：{detail}")


class MissingKey(DylanError):
    category = "缺少密钥"


class AuthFailed(DylanError):
    category = "认证失败"


class TimeoutError_(DylanError):
    category = "超时"


class ServiceError(DylanError):
    category = "服务错误"


class NetworkError(DylanError):
    category = "网络中断"


class IncompleteReply(DylanError):
    category = "网络中断"


class StoreCorrupt(DylanError):
    category = "记忆库损坏"


class WriteFailed(DylanError):
    category = "写入失败"


class MissingStore(DylanError):
    category = "记忆库不存在"


class LockedBrain(DylanError):
    category = "已有一个 dylan 在使用这块大脑"
