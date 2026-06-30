"""Pure monster breeding and personality inheritance helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .battle_model import MonsterInstance, RandomLike
from .companion_mind import (
    TRAIT_REGISTRY,
    CompanionMind,
    LearnedWeights,
    Temperament,
    TraitId,
)

TEMPERAMENT_JITTER = 4.0
TRAIT_PASS_CHANCE = 0.60
TRAIT_MUTATION_CHANCE = 0.15
MAX_INHERITED_TRAITS = 2
LEARNED_INHERIT_FRACTION = 0.25
BORN_INTO_CARE_TRUST = 35.0
BORN_INTO_CARE_BOND = 15.0
OFFSPRING_START_LEVEL = 1


@dataclass(frozen=True, slots=True)
class BreedingParent:
    monster: MonsterInstance
    mind: CompanionMind


def _clamp_stat(value: float, *, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _traits_conflict(candidate: TraitId, selected: Sequence[TraitId]) -> bool:
    definition = TRAIT_REGISTRY.get(candidate)
    if definition is None:
        return True
    for trait_id in selected:
        if trait_id in definition.conflicts:
            return True
        other = TRAIT_REGISTRY.get(trait_id)
        if other is not None and candidate in other.conflicts:
            return True
    return False


def _inherit_temperament(parent_a: CompanionMind, parent_b: CompanionMind, rng: RandomLike) -> Temperament:
    avg_aggression = (parent_a.temperament.aggression + parent_b.temperament.aggression) / 2.0
    avg_fear = (parent_a.temperament.fear + parent_b.temperament.fear) / 2.0
    aggression_jitter = (float(rng.random()) * 2.0 - 1.0) * TEMPERAMENT_JITTER
    fear_jitter = (float(rng.random()) * 2.0 - 1.0) * TEMPERAMENT_JITTER
    return Temperament(
        aggression=_clamp_stat(avg_aggression + aggression_jitter),
        fear=_clamp_stat(avg_fear + fear_jitter),
    )


def _inherit_traits(parent_a: CompanionMind, parent_b: CompanionMind, rng: RandomLike) -> tuple[TraitId, ...]:
    selected: list[TraitId] = []
    for trait_id in (*parent_a.traits, *parent_b.traits):
        if trait_id in selected:
            continue
        if float(rng.random()) >= TRAIT_PASS_CHANCE:
            continue
        if len(selected) >= MAX_INHERITED_TRAITS:
            break
        if _traits_conflict(trait_id, selected):
            continue
        selected.append(trait_id)

    if len(selected) < MAX_INHERITED_TRAITS and float(rng.random()) < TRAIT_MUTATION_CHANCE:
        pool = [trait_id for trait_id in TRAIT_REGISTRY if trait_id not in selected and not _traits_conflict(trait_id, selected)]
        if pool:
            index = int(float(rng.random()) * len(pool)) % len(pool)
            selected.append(pool[index])

    return tuple(selected[:MAX_INHERITED_TRAITS])


def _inherit_learned(parent_a: CompanionMind, parent_b: CompanionMind) -> LearnedWeights:
    attack = (parent_a.learned.ATTACK + parent_b.learned.ATTACK) / 2.0 * LEARNED_INHERIT_FRACTION
    defend = (parent_a.learned.DEFEND + parent_b.learned.DEFEND) / 2.0 * LEARNED_INHERIT_FRACTION
    hesitate = (parent_a.learned.HESITATE + parent_b.learned.HESITATE) / 2.0 * LEARNED_INHERIT_FRACTION
    return LearnedWeights(ATTACK=attack, DEFEND=defend, HESITATE=hesitate)


def _offspring_species(parent_a: BreedingParent, parent_b: BreedingParent, rng: RandomLike) -> MonsterInstance:
    chosen = parent_a if float(rng.random()) < 0.5 else parent_b
    species = chosen.monster.species
    learnset = species.learnset or ("tackle",)
    known_moves = (learnset[0],) if learnset else ()
    return MonsterInstance(species, level=OFFSPRING_START_LEVEL, known_moves=known_moves)


def breed_offspring(
    parent_a: BreedingParent,
    parent_b: BreedingParent,
    rng: RandomLike,
) -> tuple[MonsterInstance, CompanionMind]:
    """Breed an offspring monster and inherited companion mind from two parents."""

    offspring = _offspring_species(parent_a, parent_b, rng)
    mind = CompanionMind(
        temperament=_inherit_temperament(parent_a.mind, parent_b.mind, rng),
        learned=_inherit_learned(parent_a.mind, parent_b.mind),
        trust=BORN_INTO_CARE_TRUST,
        bond=BORN_INTO_CARE_BOND,
        mood=0.0,
        traits=_inherit_traits(parent_a.mind, parent_b.mind, rng),
        last_behavior=None,
    )
    return offspring, mind
