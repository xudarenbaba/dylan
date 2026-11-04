CREATE TABLE meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL,
    brain_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    privacy_notice_shown INTEGER NOT NULL DEFAULT 0,
    identity_text TEXT NOT NULL DEFAULT '',
    identity_hash TEXT NOT NULL DEFAULT '',
    user_id TEXT,
    self_id TEXT,
    baseline_mood TEXT NOT NULL DEFAULT '开朗',
    mood TEXT,
    settled_at TEXT NOT NULL,
    slept_at TEXT,
    last_session_end TEXT
);

CREATE TABLE neurons (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    innate INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (kind, name_key)
);

CREATE TABLE aliases (
    neuron_id TEXT NOT NULL REFERENCES neurons(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_key TEXT NOT NULL,
    PRIMARY KEY (neuron_id, alias_key)
);
CREATE INDEX aliases_by_key ON aliases (alias_key);

CREATE TABLE synapses (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES neurons(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES neurons(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    base_weight REAL NOT NULL CHECK (base_weight >= 0 AND base_weight <= 1),
    rehearsal_count INTEGER NOT NULL DEFAULT 0,
    innate INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_activated_at TEXT NOT NULL,
    UNIQUE (source_id, target_id, type),
    CHECK (source_id != target_id)
);
CREATE INDEX synapses_by_source ON synapses (source_id);
CREATE INDEX synapses_by_target ON synapses (target_id);

CREATE TABLE fibers (
    id TEXT PRIMARY KEY,
    anchor_id TEXT NOT NULL UNIQUE REFERENCES neurons(id),
    memory_type TEXT NOT NULL,
    about TEXT NOT NULL,
    statement TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    gist TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    importance INTEGER NOT NULL,
    emotion TEXT,
    confidence REAL,
    strength REAL NOT NULL CHECK (strength >= 0 AND strength <= 1),
    stage TEXT NOT NULL,
    detail_level INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    occurred_start TEXT,
    occurred_end TEXT,
    due_at TEXT,
    trigger TEXT NOT NULL DEFAULT '',
    valid_until TEXT,
    session_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    state_changed_at TEXT NOT NULL,
    last_recalled_at TEXT,
    recall_count INTEGER NOT NULL DEFAULT 0,
    recall_days TEXT NOT NULL DEFAULT '[]',
    settled_at TEXT NOT NULL
);
CREATE INDEX fibers_by_state ON fibers (state);

CREATE TABLE fiber_neurons (
    fiber_id TEXT NOT NULL REFERENCES fibers(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    neuron_id TEXT NOT NULL REFERENCES neurons(id) ON DELETE CASCADE,
    PRIMARY KEY (fiber_id, position)
);
CREATE INDEX fiber_neurons_by_neuron ON fiber_neurons (neuron_id);

CREATE TABLE fiber_synapses (
    fiber_id TEXT NOT NULL REFERENCES fibers(id) ON DELETE CASCADE,
    synapse_id TEXT NOT NULL REFERENCES synapses(id) ON DELETE CASCADE,
    PRIMARY KEY (fiber_id, synapse_id)
);
CREATE INDEX fiber_synapses_by_synapse ON fiber_synapses (synapse_id);

CREATE TABLE cues (
    fiber_id TEXT NOT NULL REFERENCES fibers(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    term_key TEXT NOT NULL,
    PRIMARY KEY (fiber_id, term_key)
);
CREATE INDEX cues_by_key ON cues (term_key);

CREATE TABLE coactivations (
    neuron_a TEXT NOT NULL,
    neuron_b TEXT NOT NULL,
    count INTEGER NOT NULL,
    last_on TEXT NOT NULL,
    PRIMARY KEY (neuron_a, neuron_b),
    CHECK (neuron_a < neuron_b)
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    summary TEXT NOT NULL DEFAULT '',
    slept INTEGER NOT NULL DEFAULT 0,
    sleep_attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    at TEXT NOT NULL,
    user_text TEXT NOT NULL,
    reply_text TEXT NOT NULL,
    noted INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX turns_by_session ON turns (session_id, position);

CREATE TABLE journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    phase TEXT NOT NULL,
    op TEXT NOT NULL,
    fiber_id TEXT,
    label TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX journal_by_fiber ON journal (fiber_id);
