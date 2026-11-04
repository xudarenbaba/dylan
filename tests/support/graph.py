"""Hand-built graphs for AC-07 and AC-20 only."""

from __future__ import annotations

from uuid import uuid4

from dylan.clock import dump_time
from dylan.memory.model import Fiber, Provenance
from dylan.memory.roles import direction_for
from dylan.memory.store import MemoryStore, day_key


def build_graph(
    store: MemoryStore,
    nodes: list[tuple[str, str]],
    links: list[tuple[str, str, str, float]],
    pathways: list[list[str]],
) -> dict[str, str]:
    ids = {content: store.ensure_neuron(kind, content).id for content, kind in nodes}
    synapses: dict[tuple[str, str, str], str] = {}
    for source, target, synapse_type, weight in links:
        created = store.add_synapse(
            ids[source],
            ids[target],
            synapse_type,
            direction=direction_for(synapse_type),
            base_weight=weight,
        )
        synapses[(source, target, synapse_type)] = created.id
    now = dump_time(store.clock.now())
    for pathway in pathways:
        neuron_ids = [ids[content] for content in pathway]
        synapse_ids = [
            synapse_id
            for (source, target, _kind), synapse_id in synapses.items()
            if source in pathway and target in pathway
        ]
        store.insert_fiber(
            Fiber(
                id=str(uuid4()),
                anchor_neuron_id=neuron_ids[0],
                neuron_ids=neuron_ids,
                synapse_ids=synapse_ids,
                conductivity=1.0,
                base_conductivity=1.0,
                summary=" / ".join(pathway),
                essence=" / ".join(pathway),
                ghost=pathway[0],
                body=" / ".join(pathway),
                memory_type="fact",
                priority=5,
                tier="warm",
                stage="episodic",
                state="active",
                created_at=now,
                decay_cursor=now,
                last_activated_at=now,
                last_conducted_at=now,
                provenance=Provenance(source="user_input", confidence="high", trust=0.9),
                recall_dates=[day_key(now)],
                frequency=1,
            )
        )
    return ids
