"""Canonical combat event names and payload keys.

This module centralizes combat event naming so emitters and listeners use one
shared contract. Aliases are preserved for backward compatibility.
"""

from __future__ import annotations

# Canonical event names.
EVENT_COMBAT_ATTACK = "combat_attack"
EVENT_COMBAT_HIT = "combat_hit"
EVENT_COMBAT_MISS = "combat_miss"
EVENT_COMBAT_DAMAGE = "combat_damage"
EVENT_COMBAT_DEATH = "combat_death"
EVENT_PROJECTILE_FIRED = "projectile_fired"
EVENT_PROJECTILE_HIT = "projectile_hit"

# Backward-compatibility aliases.
EVENT_DAMAGE_APPLIED_ALIAS = "damage_applied"
EVENT_DIED_ALIAS = "died"

# Common payload keys.
KEY_ATTACKER = "attacker"
KEY_SOURCE = "source"
KEY_TARGET = "target"
KEY_AMOUNT = "amount"
KEY_WAS_CRIT = "was_crit"
KEY_DAMAGE = "damage"
KEY_ENTITY = "entity"
KEY_NAME = "name"

_ALIAS_TO_CANONICAL: dict[str, str] = {
    EVENT_DAMAGE_APPLIED_ALIAS: EVENT_COMBAT_DAMAGE,
    EVENT_DIED_ALIAS: EVENT_COMBAT_DEATH,
}

COMBAT_DAMAGE_EVENT_TYPES: tuple[str, ...] = (
    EVENT_COMBAT_DAMAGE,
    EVENT_DAMAGE_APPLIED_ALIAS,
)

COMBAT_DEATH_EVENT_TYPES: tuple[str, ...] = (
    EVENT_COMBAT_DEATH,
    EVENT_DIED_ALIAS,
)


def canonicalize_combat_event_name(event_type: str) -> str:
    """Return canonical combat event name while preserving unknown values."""
    normalized = str(event_type or "").strip()
    if not normalized:
        return ""
    return _ALIAS_TO_CANONICAL.get(normalized, normalized)


def is_combat_damage_event(event_type: str) -> bool:
    """Return True when event_type is a known damage event or alias."""
    return canonicalize_combat_event_name(event_type) == EVENT_COMBAT_DAMAGE


def is_combat_death_event(event_type: str) -> bool:
    """Return True when event_type is a known death event or alias."""
    return canonicalize_combat_event_name(event_type) == EVENT_COMBAT_DEATH

