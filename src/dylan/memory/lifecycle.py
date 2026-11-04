"""Pin, freeze, thaw, recover and soft delete."""

from __future__ import annotations

from datetime import timedelta

from dylan.clock import dump_time, load_time
from dylan.memory.constants import SOFT_DELETE_GRACE_DAYS
from dylan.memory.model import Fiber
from dylan.memory.store import MemoryStore


def _refuses(fiber: Fiber) -> bool:
    return fiber.pinned or fiber.memory_type in {"identity", "boundary"}


def soft_delete(store: MemoryStore, fiber: Fiber) -> tuple[Fiber | None, str]:
    if _refuses(fiber):
        return None, "这条是钉住的，没有忘掉"
    now = dump_time(store.clock.now())
    updated = fiber.model_copy(update={"state": "soft_deleted", "deleted_at": now})
    store.save_fiber(updated)
    return updated, ""


def recover(
    store: MemoryStore, fiber: Fiber, *, grace_days: float = SOFT_DELETE_GRACE_DAYS
) -> tuple[Fiber | None, str]:
    if fiber.state != "soft_deleted" or not fiber.deleted_at:
        return None, "没有可恢复的记忆"
    deadline = load_time(fiber.deleted_at) + timedelta(days=grace_days)
    if store.clock.now() > deadline:
        return None, "宽限已过"
    updated = fiber.model_copy(update={"state": "active", "deleted_at": None})
    store.save_fiber(updated)
    return updated, ""


def freeze(store: MemoryStore, fiber: Fiber) -> Fiber:
    updated = fiber.model_copy(update={"state": "frozen"})
    store.save_fiber(updated)
    return updated


def thaw(store: MemoryStore, fiber: Fiber) -> Fiber:
    updated = fiber.model_copy(update={"state": "active"})
    store.save_fiber(updated)
    return updated


def pin(store: MemoryStore, fiber: Fiber) -> Fiber:
    updated = fiber.model_copy(update={"pinned": True, "tier": "hot"})
    store.save_fiber(updated)
    return updated


def expire_due(store: MemoryStore) -> None:
    now = store.clock.now()
    for fiber in store.fibers():
        if fiber.state != "active" or not fiber.expires_at:
            continue
        if load_time(fiber.expires_at) <= now:
            updated = fiber.model_copy(
                update={"state": "soft_deleted", "deleted_at": fiber.expires_at}
            )
            store.save_fiber(updated)
