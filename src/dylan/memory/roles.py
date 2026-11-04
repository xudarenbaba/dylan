"""Synapse roles, directions and required inverse edges."""

from __future__ import annotations

from dylan.memory.constants import (
    BIDIRECTIONAL_TYPES,
    DEPTH3_TYPES,
    INVERSE_TYPES,
    LATERAL_TYPES,
    PASSIVE_TYPES,
    REINFORCE_TYPES,
    SEQUENTIAL_TYPES,
    SUPERSEDE_SOURCE_TYPES,
    SUPERSEDE_TARGET_TYPES,
    WEAKEN_TYPES,
)


def direction_for(synapse_type: str) -> str:
    if synapse_type in BIDIRECTIONAL_TYPES:
        return "bi"
    return "uni"


def inverse_type(synapse_type: str) -> str | None:
    return INVERSE_TYPES.get(synapse_type)


def can_traverse(synapse_type: str, depth: int) -> bool:
    if synapse_type in PASSIVE_TYPES:
        return False
    if synapse_type in DEPTH3_TYPES and depth < 3:
        return False
    return True


def is_lateral(synapse_type: str) -> bool:
    return synapse_type in LATERAL_TYPES


def is_weaken(synapse_type: str) -> bool:
    return synapse_type in WEAKEN_TYPES


def is_reinforce(synapse_type: str) -> bool:
    return synapse_type in REINFORCE_TYPES


def is_sequential(synapse_type: str) -> bool:
    return synapse_type in SEQUENTIAL_TYPES


def is_supersede_source(synapse_type: str) -> bool:
    return synapse_type in SUPERSEDE_SOURCE_TYPES


def is_supersede_target(synapse_type: str) -> bool:
    return synapse_type in SUPERSEDE_TARGET_TYPES
