"""Development commands. They do not open a model client."""

from __future__ import annotations

from dylan.memory.consolidate.runner import run_all, run_strategies
from dylan.memory.decay import apply_decay
from dylan.memory.health import report
from dylan.memory.lifecycle import freeze, recover, thaw
from dylan.memory.limits import Limits
from dylan.memory.model import Fiber
from dylan.memory.store import MemoryStore


def show_status(store: MemoryStore, stdout: object) -> int:
    fibers, neurons = store.counts()
    identity = "在" if store.identity_pinned() else "不在"
    stdout.write(f"纤维: {fibers}\n神经元: {neurons}\n身份: {identity}\n")  # type: ignore[attr-defined]
    return 0


def show_health(store: MemoryStore, stdout: object, limits: Limits) -> int:
    payload = report(store, limits)
    for key in ("成熟比例", "连通", "新鲜", "冲突", "建议"):
        stdout.write(f"{key}: {payload[key]}\n")  # type: ignore[attr-defined]
    return 0


def run_decay(store: MemoryStore, stdout: object) -> int:
    apply_decay(store)
    stdout.write("衰减已结算\n")  # type: ignore[attr-defined]
    return 0


def run_prune(store: MemoryStore, stdout: object, *, dry_run: bool, limits: Limits) -> int:
    done = run_strategies(store, ["prune"], dry_run=dry_run, limits=limits)
    stdout.write(f"修剪: {done[0][1]}\n")  # type: ignore[attr-defined]
    return 0


def run_consolidate(
    store: MemoryStore,
    stdout: object,
    *,
    names: list[str],
    dry_run: bool,
    limits: Limits,
    compressor: object | None = None,
) -> int:
    if names == ["all"]:
        done = run_all(store, dry_run=dry_run, limits=limits, compressor=compressor)  # type: ignore[arg-type]
    else:
        done = run_strategies(
            store,
            names,
            dry_run=dry_run,
            limits=limits,
            compressor=compressor,  # type: ignore[arg-type]
        )
    for name, count in done:
        stdout.write(f"{name}: {count}\n")  # type: ignore[attr-defined]
    return 0


def run_lifecycle(
    store: MemoryStore,
    stdout: object,
    stderr: object,
    *,
    action: str,
    fiber_id: str | None,
    match: str | None,
    limits: Limits,
) -> int:
    if not fiber_id and not match:
        stderr.write("需要 --id 或 --match\n")  # type: ignore[attr-defined]
        return 1
    found = _select(store, fiber_id, match)
    if len(found) != 1:
        if not found:
            stderr.write("没有匹配的记忆\n")  # type: ignore[attr-defined]
        else:
            for fiber in found:
                stdout.write(f"{fiber.id} {fiber.summary}\n")  # type: ignore[attr-defined]
            stderr.write("命中不止一条\n")  # type: ignore[attr-defined]
        return 1
    fiber = found[0]
    if action == "freeze":
        freeze(store, fiber)
    elif action == "thaw":
        thaw(store, fiber)
    else:
        updated, reason = recover(store, fiber, grace_days=limits.grace_days)
        if updated is None:
            stderr.write(reason + "\n")  # type: ignore[attr-defined]
            return 1
    stdout.write("完成\n")  # type: ignore[attr-defined]
    return 0


def _select(store: MemoryStore, fiber_id: str | None, match: str | None) -> list[Fiber]:
    fibers = store.fibers()
    if fiber_id:
        return [fiber for fiber in fibers if fiber.id == fiber_id]
    assert match is not None
    return [
        fiber
        for fiber in fibers
        if match in fiber.id or match in fiber.summary or match in (fiber.body or "")
    ]
