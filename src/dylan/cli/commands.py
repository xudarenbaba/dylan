"""Development commands. None of them opens a model client."""

from __future__ import annotations

from datetime import tzinfo

from dylan.memory.constants import MEMORY_TYPES, STAGES, STATES
from dylan.memory.store import MemoryStore


def show_status(store: MemoryStore, stdout: object, tz: tzinfo) -> int:
    counts = store.counts()
    meta = store.meta()
    fibers = store.fibers()
    lines = [
        f"出生：{'是' if store.born() else '否'}",
        f"神经元：{counts['neurons']}",
        f"突触：{counts['synapses']}",
        f"记忆：{counts['fibers']}",
        f"会话：{counts['sessions']}",
        f"待整理的会话：{sum(1 for session in store.sessions() if not session.slept)}",
        f"日志：{counts['journal']}",
        f"心情底色：{meta['baseline_mood']}",
    ]
    by_type: dict[str, int] = {}
    by_state: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    for fiber in fibers:
        by_type[fiber.memory_type] = by_type.get(fiber.memory_type, 0) + 1
        by_state[fiber.state] = by_state.get(fiber.state, 0) + 1
        by_stage[fiber.stage] = by_stage.get(fiber.stage, 0) + 1
    if by_type:
        def joined(names: dict[str, str], counts: dict[str, int]) -> str:
            return "，".join(f"{names.get(key, key)} {value}" for key, value in counts.items())

        lines.append("类型：" + joined(MEMORY_TYPES, by_type))
        lines.append("状态：" + joined(STATES, by_state))
        lines.append("阶段：" + joined(STAGES, by_stage))
    stdout.write("\n".join(lines) + "\n")  # type: ignore[attr-defined]
    return 0
