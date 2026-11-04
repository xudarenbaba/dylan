"""Weight updates. Base weight changes; effective weight is recomputed."""

from __future__ import annotations

from dylan.clock import dump_time
from dylan.memory.constants import HEBBIAN_ETA
from dylan.memory.decay import effective_weight
from dylan.memory.model import Synapse
from dylan.memory.store import MemoryStore


def reinforce(store: MemoryStore, synapse: Synapse, pre: float | None, post: float | None) -> None:
    if pre is None or post is None:
        delta = HEBBIAN_ETA
    else:
        delta = HEBBIAN_ETA * pre * post * (1.0 - synapse.base_weight)
    now = dump_time(store.clock.now())
    synapse.base_weight = min(1.0, synapse.base_weight + delta)
    synapse.rehearsal_count += 1
    synapse.last_activated_at = now
    synapse.decay_cursor = now
    synapse.weight = effective_weight(synapse, store.clock.now())
    store.save_synapse(synapse)
