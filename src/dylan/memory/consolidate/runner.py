"""Short consolidation, one named strategy, or the full sequence except dream."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from dylan.memory.consolidate.compress import TextCompressor
from dylan.memory.constants import ALL_STRATEGIES, EXTRA_STRATEGIES, SHORT_CONSOLIDATION
from dylan.memory.health import report
from dylan.memory.limits import Limits
from dylan.memory.store import MemoryStore

from . import (
    compress,
    dedup,
    dream,
    enrich,
    habits,
    infer,
    mature,
    merge,
    prune,
    semantic_link,
    summarize,
)

Handler = Callable[[MemoryStore], int]


def _handlers(compressor: TextCompressor | None, limits: Limits) -> dict[str, Handler]:
    return {
        "dedup": lambda store: dedup.run(store, limits),
        "merge": lambda store: merge.run(store, limits),
        "enrich": enrich.run,
        "infer": infer.run,
        "semantic_link": lambda store: semantic_link.run(store, limits),
        "learn_habits": habits.run,
        "summarize": summarize.run,
        "mature": mature.run,
        "compress": lambda store: compress.run(store, compressor),
        "prune": lambda store: prune.run(store, limits),
        "dream": dream.run,
    }


def run_strategies(
    store: MemoryStore,
    names: Sequence[str],
    *,
    dry_run: bool = False,
    compressor: TextCompressor | None = None,
    limits: Limits | None = None,
) -> list[tuple[str, int]]:
    limits = limits or Limits()
    handlers = _handlers(compressor, limits)

    def apply() -> list[tuple[str, int]]:
        done: list[tuple[str, int]] = []
        for name in names:
            if name not in handlers:
                raise ValueError(name)
            done.append((name, handlers[name](store)))
        return done

    if dry_run:
        store.hold_transaction()
        try:
            return apply()
        finally:
            store.rollback_outer()
    with store.transaction():
        return apply()


def run_all(
    store: MemoryStore,
    *,
    dry_run: bool = False,
    compressor: TextCompressor | None = None,
    limits: Limits | None = None,
) -> list[tuple[str, int]]:
    return run_strategies(
        store,
        ALL_STRATEGIES,
        dry_run=dry_run,
        compressor=compressor,
        limits=limits,
    )


def short_consolidation(
    store: MemoryStore,
    *,
    auto_dream: bool = False,
    compressor: TextCompressor | None = None,
    limits: Limits | None = None,
) -> list[tuple[str, int]]:
    limits = limits or Limits()
    done = run_strategies(
        store,
        SHORT_CONSOLIDATION,
        compressor=compressor,
        limits=limits,
    )
    suggestion = str(report(store, limits)["建议"])
    if suggestion in EXTRA_STRATEGIES:
        done.extend(
            run_strategies(store, [suggestion], compressor=compressor, limits=limits)
        )
    if auto_dream:
        done.extend(run_strategies(store, ["dream"], compressor=compressor, limits=limits))
    return done
