"""Pure breeding-shrine attempt logic."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Literal, MutableMapping

from .battle_model import RandomLike
from .breeding import BreedingParent, breed_offspring
from .collection import (
    MONSTER_PARTY_KEY,
    ensure_monster_collection,
    load_companion_mind_for_instance,
)
from .companion_mind import CompanionMind
from .data_load import MonsterCatalog
from .egg_lifecycle import MONSTER_EGGS_KEY, create_breeding_egg, ensure_egg_collection, load_monster_instance_from_values

BreedingShrineOutcome = Literal[
    "success",
    "not_enough_bonded",
    "egg_waiting",
    "catalog_error",
    "party_error",
]


@dataclass(frozen=True, slots=True)
class BreedingShrineResult:
    outcome: BreedingShrineOutcome
    egg_id: str = ""
    species_id: str = ""
    parent_a_instance_id: str = ""
    parent_b_instance_id: str = ""


def count_pending_eggs(values: MutableMapping[str, Any]) -> int:
    ensure_egg_collection(values)
    eggs = values.get(MONSTER_EGGS_KEY)
    if not isinstance(eggs, list):
        return 0
    return sum(1 for egg in eggs if isinstance(egg, dict))


def _qualifying_party_pairs(
    values: MutableMapping[str, Any],
    *,
    species_by_id: dict[str, Any],
    bond_threshold: float,
) -> list[tuple[str, str, float, float]]:
    ensure_monster_collection(values)
    party_ids = [str(instance_id) for instance_id in values.get(MONSTER_PARTY_KEY, []) if str(instance_id).strip()]
    qualified: list[tuple[str, str, float]] = []
    for instance_id in party_ids:
        monster = load_monster_instance_from_values(values, instance_id, species_by_id=species_by_id)
        if monster is None or monster.fainted:
            continue
        mind = load_companion_mind_for_instance(values, instance_id)
        if mind is None:
            continue
        bond = float(mind.bond)
        if bond < bond_threshold:
            continue
        qualified.append((instance_id, monster.species.id, bond))

    if len(qualified) < 2:
        return []

    qualified.sort(key=lambda row: row[2], reverse=True)
    first_id, first_species, first_bond = qualified[0]
    second_id, second_species, second_bond = qualified[1]
    return [(first_id, second_id, first_bond, second_bond)]


def attempt_breeding_at_shrine(
    values: MutableMapping[str, Any],
    *,
    catalog: MonsterCatalog,
    bond_threshold: float = 50.0,
    max_eggs: int = 1,
    hatch_steps: int = 200,
    rng: RandomLike | None = None,
) -> BreedingShrineResult:
    """Try to create a breeding egg from the two strongest bonded party members."""

    if catalog is None or not catalog.species:
        return BreedingShrineResult(outcome="catalog_error")

    if count_pending_eggs(values) >= max(1, int(max_eggs)):
        return BreedingShrineResult(outcome="egg_waiting")

    pairs = _qualifying_party_pairs(values, species_by_id=catalog.species, bond_threshold=float(bond_threshold))
    if not pairs:
        return BreedingShrineResult(outcome="not_enough_bonded")

    parent_a_id, parent_b_id, _, _ = pairs[0]
    parent_a_monster = load_monster_instance_from_values(values, parent_a_id, species_by_id=catalog.species)
    parent_b_monster = load_monster_instance_from_values(values, parent_b_id, species_by_id=catalog.species)
    if parent_a_monster is None or parent_b_monster is None:
        return BreedingShrineResult(outcome="party_error")

    default_mind = CompanionMind()
    parent_a_mind = load_companion_mind_for_instance(values, parent_a_id) or default_mind
    parent_b_mind = load_companion_mind_for_instance(values, parent_b_id) or default_mind
    source_rng = rng if rng is not None else random.Random()

    offspring, mind = breed_offspring(
        BreedingParent(parent_a_monster, parent_a_mind),
        BreedingParent(parent_b_monster, parent_b_mind),
        source_rng,
    )
    egg_id = create_breeding_egg(
        values,
        offspring=offspring,
        mind=mind,
        parent_a_instance_id=parent_a_id,
        parent_b_instance_id=parent_b_id,
        hatch_steps=max(1, int(hatch_steps)),
    )
    return BreedingShrineResult(
        outcome="success",
        egg_id=egg_id,
        species_id=offspring.species.id,
        parent_a_instance_id=parent_a_id,
        parent_b_instance_id=parent_b_id,
    )
