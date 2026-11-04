CREATE TABLE meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL,
    brain_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    privacy_notice_shown INTEGER NOT NULL DEFAULT 0,
    last_decay_at TEXT
);

CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    content_key TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE (kind, content_key)
);

CREATE TABLE synapses (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES neurons(id),
    target_id TEXT NOT NULL REFERENCES neurons(id),
    type TEXT NOT NULL,
    direction TEXT NOT NULL,
    base_weight REAL NOT NULL CHECK (base_weight >= 0 AND base_weight <= 1),
    weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
    rehearsal_count INTEGER NOT NULL DEFAULT 0,
    last_activated_at TEXT,
    decay_cursor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (source_id, target_id, type),
    CHECK (source_id != target_id)
);

CREATE TABLE fibers (
    id TEXT PRIMARY KEY,
    anchor_neuron_id TEXT NOT NULL REFERENCES neurons(id),
    conductivity REAL NOT NULL,
    base_conductivity REAL NOT NULL,
    coherence REAL NOT NULL DEFAULT 1,
    salience REAL NOT NULL DEFAULT 0.5,
    frequency INTEGER NOT NULL DEFAULT 1,
    summary TEXT NOT NULL,
    essence TEXT NOT NULL DEFAULT '',
    ghost TEXT NOT NULL DEFAULT '',
    body TEXT,
    compression_tier INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    priority INTEGER NOT NULL,
    tier TEXT NOT NULL,
    state TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 0,
    time_start TEXT,
    time_end TEXT,
    expires_at TEXT,
    rehearsal_count INTEGER NOT NULL DEFAULT 0,
    last_conducted_at TEXT,
    last_activated_at TEXT,
    created_at TEXT NOT NULL,
    decay_cursor TEXT NOT NULL,
    deleted_at TEXT,
    provenance TEXT NOT NULL,
    recall_dates TEXT NOT NULL DEFAULT '[]',
    confidence_value REAL,
    auto_session INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE fiber_neurons (
    fiber_id TEXT NOT NULL REFERENCES fibers(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    neuron_id TEXT NOT NULL REFERENCES neurons(id),
    PRIMARY KEY (fiber_id, position)
);

CREATE TABLE fiber_synapses (
    fiber_id TEXT NOT NULL REFERENCES fibers(id) ON DELETE CASCADE,
    synapse_id TEXT NOT NULL REFERENCES synapses(id) ON DELETE CASCADE,
    PRIMARY KEY (fiber_id, synapse_id)
);

CREATE TABLE fiber_tags (
    fiber_id TEXT NOT NULL REFERENCES fibers(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (fiber_id, tag)
);

CREATE TABLE coactivations (
    neuron_a TEXT NOT NULL,
    neuron_b TEXT NOT NULL,
    count INTEGER NOT NULL,
    last_on TEXT NOT NULL,
    PRIMARY KEY (neuron_a, neuron_b),
    CHECK (neuron_a < neuron_b)
);

CREATE TABLE sequence_observations (
    signature TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (signature, day)
);

CREATE TABLE recall_runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE recall_hits (
    run_id TEXT NOT NULL REFERENCES recall_runs(run_id) ON DELETE CASCADE,
    neuron_id TEXT NOT NULL,
    PRIMARY KEY (run_id, neuron_id)
);
