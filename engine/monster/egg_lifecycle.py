"""Egg collection helpers for bred monster offspring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

from .battle_model import MonsterInstance, Species
from .collection import (
    MONSTER_INSTANCES_KEY,
    add_caught_monster,
    companion_mind_to_dict,
    ensure_monster_collection,
    load_companion_mind_for_instance,
    persist_companion_mind,
    serialize_monster_instance,
)
from .companion_mind import CompanionMind, companion_mind_from_dict

MONSTER_EGGS_KEY = "monster_eggs"
DEFAULT_EGG_HATCH_STEPS = 80
OFFSPRING_KEY = "offspring"
COMPANION_MIND_KEY = "companion_mind"
STEPS_REMAINING_KEY = "steps_remaining"
HATCH_STEPS_KEY = "hatch_steps"
EGG_ID_KEY = "egg_id"
PARENT_A_INSTANCE_ID_KEY = "parent_a_instance_id"
PARENT_B_INSTANCE_ID_KEY = "parent_b_instance_id"


@dataclass(frozen=True, slots=True)
class HatchEvent:
    egg_id: str
    instance_id: str
    storage: str
    species_id: str
    mind: CompanionMind


def ensure_egg_collection(values: MutableMapping[str, Any]) -> None:
    ensure_monster_collection(values)
    if not isinstance(values.get(MONSTER_EGGS_KEY), list):
        values[MONSTER_EGGS_KEY] = []


def _next_egg_id(values: MutableMapping[str, Any]) -> str:
    ensure_egg_collection(values)
    eggs = values[MONSTER_EGGS_KEY]
    index = 1
    existing = {
        str(egg.get(EGG_ID_KEY))
        for egg in eggs
        if isinstance(egg, dict) and egg.get(EGG_ID_KEY) is not None
    }
    while True:
        candidate = f"egg_{index:04d}"
        if candidate not in existing:
            return candidate
        index += 1


def create_breeding_egg(
    values: MutableMapping[str, Any],
    *,
    offspring: MonsterInstance,
    mind: CompanionMind,
    parent_a_instance_id: str | None = None,
    parent_b_instance_id: str | None = None,
    hatch_steps: int = DEFAULT_EGG_HATCH_STEPS,
) -> str:
    """Store a bred offspring egg in game-state values."""

    ensure_egg_collection(values)
    steps = max(1, int(hatch_steps))
    egg_id = _next_egg_id(values)
    payload = {
        EGG_ID_KEY: egg_id,
        STEPS_REMAINING_KEY: steps,
        HATCH_STEPS_KEY: steps,
        OFFSPRING_KEY: serialize_monster_instance(offspring, companion_mind=companion_mind_to_dict(mind)),
        COMPANION_MIND_KEY: companion_mind_to_dict(mind),
        PARENT_A_INSTANCE_ID_KEY: str(parent_a_instance_id or ""),
        PARENT_B_INSTANCE_ID_KEY: str(parent_b_instance_id or ""),
    }
    values[MONSTER_EGGS_KEY].append(payload)
    return egg_id


def _monster_from_row(row: Mapping[str, Any], species_by_id: Mapping[str, Species]) -> MonsterInstance | None:
    species_id = str(row.get("species_id", ""))
    species = species_by_id.get(species_id)
    if species is None:
        return None
    known_moves = row.get("known_moves")
    moves = tuple(str(move_id) for move_id in known_moves) if isinstance(known_moves, list) else species.learnset
    return MonsterInstance(
        species,
        level=int(row.get("level", 1) or 1),
        current_hp=int(row.get("current_hp", 0) or 0),
        known_moves=moves,
        experience=int(row.get("xp", row.get("experience", 0)) or 0),
    )


def _hatch_egg(
    values: MutableMapping[str, Any],
    egg: dict[str, Any],
    *,
    species_by_id: Mapping[str, Species],
) -> HatchEvent | None:
    offspring_row = egg.get(OFFSPRING_KEY)
    if not isinstance(offspring_row, dict):
        return None
    offspring = _monster_from_row(offspring_row, species_by_id)
    if offspring is None:
        return None

    mind_payload = egg.get(COMPANION_MIND_KEY, offspring_row.get("companion_mind"))
    mind = companion_mind_from_dict(mind_payload) if isinstance(mind_payload, dict) else CompanionMind()

    stored = add_caught_monster(values, offspring)
    persist_companion_mind(values, stored.instance_id, mind)
    return HatchEvent(
        egg_id=str(egg.get(EGG_ID_KEY, "")),
        instance_id=stored.instance_id,
        storage=stored.storage,
        species_id=offspring.species.id,
        mind=mind,
    )


def tick_monster_eggs(
    values: MutableMapping[str, Any],
    *,
    species_by_id: Mapping[str, Species],
    steps: int = 1,
) -> list[HatchEvent]:
    """Advance egg timers and hatch any eggs that reach zero steps remaining."""

    ensure_egg_collection(values)
    tick_count = max(1, int(steps))
    hatched: list[HatchEvent] = []
    remaining: list[dict[str, Any]] = []

    for raw in values[MONSTER_EGGS_KEY]:
        if not isinstance(raw, dict):
            continue
        egg = dict(raw)
        steps_left = max(0, int(egg.get(STEPS_REMAINING_KEY, 0) or 0) - tick_count)
        egg[STEPS_REMAINING_KEY] = steps_left
        if steps_left <= 0:
            event = _hatch_egg(values, egg, species_by_id=species_by_id)
            if event is not None:
                hatched.append(event)
            continue
        remaining.append(egg)

    values[MONSTER_EGGS_KEY] = remaining
    return hatched


def load_monster_instance_from_values(
    values: MutableMapping[str, Any],
    instance_id: str,
    *,
    species_by_id: Mapping[str, Species],
) -> MonsterInstance | None:
    ensure_monster_collection(values)
    row = values[MONSTER_INSTANCES_KEY].get(str(instance_id))
    if not isinstance(row, dict):
        return None
    return _monster_from_row(row, species_by_id)
