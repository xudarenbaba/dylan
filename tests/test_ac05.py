"""AC-05: decay is idempotent. Identity does not move. Synapse rows are not rewritten."""

from dylan.memory.decay import apply_decay
from dylan.memory.encode import Draft, write_draft


def test_context_decays_identity_does_not_and_second_pass_is_stable(store, clock) -> None:
    context = write_draft(
        store,
        Draft(
            memory_type="context",
            summary="今天下雨了",
            body="今天下雨了",
            neurons=[("concept", "今天下雨了")],
        ),
    )
    assert context is not None
    identity = next(fiber for fiber in store.fibers() if fiber.memory_type == "identity")
    row = store.conn.execute("SELECT id, base_weight, weight FROM synapses LIMIT 1").fetchone()
    clock.advance(days=30)
    apply_decay(store)
    decayed = store.fiber(context.id)
    assert decayed is not None
    assert decayed.conductivity < 1.0
    assert store.fiber(identity.id).conductivity == 1.0
    column = store.conn.execute(
        "SELECT base_weight, weight FROM synapses WHERE id = ?",
        (row["id"],),
    ).fetchone()
    assert column["base_weight"] == row["base_weight"]
    assert column["weight"] == row["weight"]
    visible = next(synapse for synapse in store.synapses() if synapse.id == row["id"])
    assert visible.base_weight == row["base_weight"]
    assert visible.weight < row["weight"]
    frozen = decayed.conductivity
    apply_decay(store)
    assert store.fiber(context.id).conductivity == frozen
    assert store.fiber(identity.id).conductivity == 1.0
