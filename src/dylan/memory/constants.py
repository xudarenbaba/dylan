"""Numeric and closed-set literals from the requirements and technical design."""

from __future__ import annotations

SCHEMA_VERSION = 1
BRAIN_NAME = "dylan"

ACTIVATION_THRESHOLD = 0.2
DECAY_RATE = 0.2
PRUNE_WEIGHT = 0.05
PRUNE_INACTIVE_DAYS = 7.0
SOFT_DELETE_GRACE_DAYS = 7.0
DEDUP_JACCARD = 0.8
MERGE_JACCARD = 0.5
TAG_JACCARD = 0.5
ANCHOR_JACCARD = 0.5
LEXICON_WEIGHT = 0.6
INFER_WEIGHT = 0.3
INFER_MIN_COUNT = 2
DREAM_LIMIT = 3
DEFAULT_SYNAPSE_WEIGHT = 0.5

RECALL_LIMIT = 5
RECALL_CHARS = 1500
HOT_CHARS = 800
BUFFER_TURNS = 12
TIMEOUT_SECONDS = 60

CLEAR_SCORE = 0.6
SCORE_FLOOR = 0.2
PRIORITY_BASE = 0.5
PRIORITY_SCALE = 20.0
DEFAULT_PRIORITY = 5
IDENTITY_PRIORITY = 10

STAGE_FACTOR = {"episodic": 1.0, "working": 1.1, "semantic": 1.25}
TIER_MULTIPLIER = {"hot": 0.5, "warm": 1.0, "cold": 2.0}
HOT_FLOOR = 0.5
SEMANTIC_FLOOR = 0.8
SEMANTIC_LAMBDA_SCALE = 0.25

HOPS = {0: 0, 1: 2, 2: 4, 3: 6}
TIME_WINDOW_DAYS = {0: 0, 1: 7, 2: 30, 3: 365}
ANCHOR_CAP = {"time": 1.0, "entity": 0.8, "workflow": 0.6, "concept": 0.4}

BOOST = 1.1
WEAKEN = 0.7
COACTIVATION_BONUS = 0.1
HEBBIAN_ETA = 0.05
CONDUCTIVITY_BUMP = 0.02
DEDUP_BUMP = 0.05

SYNAPSE_HALF_LIFE_HOURS = 1440.0
SYNAPSE_HALF_LIFE_GROWTH = 0.5
SYNAPSE_FLOOR_BASE = 0.3
SYNAPSE_FLOOR_STEP = 0.05
SYNAPSE_FLOOR_CAP = 0.5

WORKING_MIN_DAYS = 3
WORKING_MIN_FREQUENCY = 3
MATURE_MIN_DAYS = 7.0
MATURE_MIN_FREQUENCY = 5
MATURE_MIN_CONDUCTIVITY = 0.6
HABIT_MIN_DAYS = 3
COMPRESS_MAX_CONDUCTIVITY = 0.2
COMPRESS_MIN_AGE_DAYS = 180.0
FRESH_DAYS = 30.0

SUMMARY_CHARS = 300
ESSENCE_CHARS = 150
GHOST_CHARS = 40
SHORT_TEXT = 2

HYPOTHESIS_PRIOR = 0.5
EVIDENCE_FOR_STEP = 0.1
EVIDENCE_AGAINST_SCALE = 0.8

TRUST_CAP = {
    "user_input": 0.9,
    "ai_inference": 0.7,
    "consolidation": 0.7,
    "dream": 0.5,
}

LAMBDA = {
    "identity": None,
    "boundary": 0.01,
    "fact": 0.02,
    "preference": 0.03,
    "decision": 0.03,
    "instruction": 0.05,
    "insight": 0.05,
    "hypothesis": 0.03,
    "schema": 0.01,
    "reference": 0.04,
    "tool": 0.06,
    "context": 0.08,
    "workflow": 0.08,
    "prediction": 0.10,
    "error": 0.12,
    "todo": 0.15,
    "episode": 0.05,
}
UNKNOWN_LAMBDA = 0.1

EXPIRY_DAYS = {
    "identity": None,
    "boundary": None,
    "fact": None,
    "preference": None,
    "decision": 90,
    "instruction": None,
    "insight": 180,
    "hypothesis": 180,
    "schema": None,
    "reference": None,
    "tool": 90,
    "context": 7,
    "workflow": 365,
    "prediction": 30,
    "error": 30,
    "todo": 30,
    "episode": None,
}

MEMORY_TYPES = frozenset(LAMBDA)
NEURON_KINDS = frozenset({"entity", "concept", "episode", "time", "emotion"})
PASSIVE_TYPES = frozenset(
    {"happened_at", "during", "alias", "stored_by", "verified_at", "approved_by"}
)
DEPTH3_TYPES = frozenset({"felt", "evokes"})
SEQUENTIAL_TYPES = frozenset({"before", "after", "caused_by", "leads_to", "enables"})
WEAKEN_TYPES = frozenset({"prevents", "contradicts", "evidence_against"})
REINFORCE_TYPES = frozenset({"evidence_for", "verified_by", "effective_for"})
SUPERSEDE_SOURCE_TYPES = frozenset({"supersedes", "evolves_from"})
SUPERSEDE_TARGET_TYPES = frozenset({"resolved_by", "falsified_by"})
LATERAL_TYPES = frozenset(
    {"co_occurs", "related_to", "similar_to", "near", "used_with"}
)
STRUCTURAL_TYPES = frozenset(
    {
        "is_a",
        "has_property",
        "involves",
        "at_location",
        "contains",
        "source_of",
        "predicted",
        "derived_from",
        "subgoal_of",
    }
)
SYNAPSE_TYPES = (
    PASSIVE_TYPES
    | DEPTH3_TYPES
    | SEQUENTIAL_TYPES
    | WEAKEN_TYPES
    | REINFORCE_TYPES
    | SUPERSEDE_SOURCE_TYPES
    | SUPERSEDE_TARGET_TYPES
    | LATERAL_TYPES
    | STRUCTURAL_TYPES
)
EXCLUDED_SYNAPSE_TYPES = frozenset(
    {
        "imports",
        "calls",
        "depends_on",
        "inherits",
        "implements",
        "defined_in",
        "raises",
        "has_value",
        "measured_at",
        "regulates",
        "in_row",
        "in_column",
    }
)
INVERSE_TYPES = {
    "before": "after",
    "after": "before",
    "caused_by": "leads_to",
    "leads_to": "caused_by",
    "contains": "at_location",
    "at_location": "contains",
}
BIDIRECTIONAL_TYPES = LATERAL_TYPES

HOT_TYPES = frozenset({"identity", "boundary", "instruction"})
PINNED_ON_CREATE = frozenset({"identity", "boundary"})

PRIVACY_NOTICE = "对话内容和被唤起的记忆会发送给 DeepSeek。"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
SECRET_PATTERN = r"sk-[A-Za-z0-9_-]{16,}"

SHORT_CONSOLIDATION = ("dedup", "prune", "mature")
EXTRA_STRATEGIES = (
    "learn_habits",
    "infer",
    "compress",
    "merge",
    "summarize",
    "semantic_link",
    "enrich",
)
ALL_STRATEGIES = (
    "dedup",
    "merge",
    "enrich",
    "infer",
    "semantic_link",
    "learn_habits",
    "summarize",
    "mature",
    "compress",
    "prune",
)

CERTAINTY_ORDER = ("inferred", "faint", "clear")
