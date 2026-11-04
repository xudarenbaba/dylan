"""AC-23: two live facts joined by contradicts are both visible to the stand-in."""

from pathlib import Path

from dylan.llm.fake import _read_thought
from dylan.memory.encode import bootstrap
from dylan.memory.roles import direction_for
from dylan.memory.store import MemoryStore
from support.identity import TEXT


def test_conflict_is_spoken_from_both_sides(tmp_path: Path, clock, invoke, make_fiber) -> None:
    db = tmp_path / "dylan.db"
    store = MemoryStore.create(db, clock)
    bootstrap(store, TEXT)
    south = store.ensure_neuron("concept", "住在南方")
    north = store.ensure_neuron("concept", "住在北方")
    store.add_synapse(
        south.id,
        north.id,
        "contradicts",
        direction=direction_for("contradicts"),
        base_weight=1.0,
    )
    make_fiber(store, "住在南方", neuron_ids=[south.id], summary="住在南方", body="住在南方")
    make_fiber(store, "住在北方", neuron_ids=[north.id], summary="住在北方", body="住在北方")
    store.close()
    _code, out, err, model = invoke(db, ["住在南方还是住在北方"])
    assert err == "" or "没有记住" not in err
    thought = _read_thought(model.seen[-1])
    assert thought["conflicts"]
    assert "住在南方" in out
    assert "住在北方" in out


def test_correction_phrase_links_the_previous_fact(store) -> None:
    from dylan.dialogue.rules import extract_rules
    from dylan.memory.encode import write_drafts

    write_drafts(store, extract_rules("我住在南方")[0])
    write_drafts(store, extract_rules("我说错了，住在北方")[0])
    facts = [
        fiber
        for fiber in store.fibers()
        if fiber.memory_type == "fact" and fiber.state == "active"
    ]
    assert len(facts) == 2
    assert any(synapse.type == "contradicts" for synapse in store.synapses())
