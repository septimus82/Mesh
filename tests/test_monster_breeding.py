"""Tests for pure monster breeding inheritance."""

from __future__ import annotations

import importlib
import random
from pathlib import Path

import pytest

from engine.monster.battle_model import BattleStats, MonsterInstance, Species
from engine.monster.breeding import (
    BORN_INTO_CARE_BOND,
    BORN_INTO_CARE_TRUST,
    LEARNED_INHERIT_FRACTION,
    MAX_INHERITED_TRAITS,
    BreedingParent,
    breed_offspring,
)
from engine.monster.companion_mind import (
    BRAVE,
    LOYAL,
    QUICK_LEARNER,
    TIMID,
    CompanionMind,
    LearnedWeights,
    Temperament,
    companion_mind_from_dict,
    companion_mind_to_dict,
)

pytestmark = pytest.mark.fast

TACKLE = ("tackle",)
SPROUT = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
    types=("grass",),
    learnset=TACKLE,
)
SHELL = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=TACKLE,
)


def _parent(
    species: Species,
    *,
    aggression: float,
    fear: float,
    traits: tuple[str, ...] = (),
    learn_attack: float = 0.0,
    learn_defend: float = 0.0,
    learn_hesitate: float = 0.0,
    level: int = 8,
) -> BreedingParent:
    return BreedingParent(
        monster=MonsterInstance(species, level=level, known_moves=species.learnset),
        mind=CompanionMind(
            temperament=Temperament(aggression=aggression, fear=fear),
            learned=LearnedWeights(ATTACK=learn_attack, DEFEND=learn_defend, HESITATE=learn_hesitate),
            trust=70.0,
            bond=55.0,
            traits=traits,
        ),
    )


def test_breeding_module_is_pure() -> None:
    module = importlib.import_module("engine.monster.breeding")
    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden = (
        "optional_arcade",
        "GameWindow",
        "battle_controller",
        "import random",
        "from random import",
    )
    for token in forbidden:
        assert token not in source


def test_breed_offspring_is_deterministic_under_seed() -> None:
    parent_a = _parent(SPROUT, aggression=60.0, fear=20.0, traits=(BRAVE,), learn_attack=40.0)
    parent_b = _parent(SHELL, aggression=30.0, fear=50.0, traits=(TIMID,), learn_defend=24.0)

    first_offspring, first_mind = breed_offspring(parent_a, parent_b, random.Random(99))
    second_offspring, second_mind = breed_offspring(parent_a, parent_b, random.Random(99))

    assert first_offspring.species.id == second_offspring.species.id
    assert companion_mind_to_dict(first_mind) == companion_mind_to_dict(second_mind)


def test_offspring_species_comes_from_a_parent() -> None:
    parent_a = _parent(SPROUT, aggression=50.0, fear=10.0)
    parent_b = _parent(SHELL, aggression=40.0, fear=15.0)

    species_ids = {
        breed_offspring(parent_a, parent_b, random.Random(seed))[0].species.id for seed in range(40)
    }

    assert species_ids.issubset({"sproutling", "shelltide"})
    assert len(species_ids) == 2


def test_offspring_starts_stranger_baseline_trust_and_bond() -> None:
    """Hatchlings deliberately start below flee threshold (director option 1: stranger baseline)."""
    parent_a = _parent(SPROUT, aggression=80.0, fear=10.0, traits=(LOYAL,))
    parent_b = _parent(SHELL, aggression=20.0, fear=80.0, traits=(QUICK_LEARNER,))

    _, mind = breed_offspring(parent_a, parent_b, random.Random(7))

    assert mind.trust == pytest.approx(BORN_INTO_CARE_TRUST)
    assert mind.bond == pytest.approx(BORN_INTO_CARE_BOND)


def test_temperament_is_parent_average_with_small_jitter() -> None:
    parent_a = _parent(SPROUT, aggression=80.0, fear=10.0)
    parent_b = _parent(SHELL, aggression=40.0, fear=30.0)

    _, mind = breed_offspring(parent_a, parent_b, random.Random(3))

    assert mind.temperament.aggression == pytest.approx(62.0, abs=4.5)
    assert mind.temperament.fear == pytest.approx(22.0, abs=4.5)


def test_learned_habits_are_fraction_of_parent_average() -> None:
    parent_a = _parent(SPROUT, aggression=50.0, fear=10.0, learn_attack=40.0, learn_defend=20.0, learn_hesitate=10.0)
    parent_b = _parent(SHELL, aggression=50.0, fear=10.0, learn_attack=20.0, learn_defend=40.0, learn_hesitate=30.0)

    _, mind = breed_offspring(parent_a, parent_b, random.Random(1))

    assert mind.learned.ATTACK == pytest.approx(30.0 * LEARNED_INHERIT_FRACTION)
    assert mind.learned.DEFEND == pytest.approx(30.0 * LEARNED_INHERIT_FRACTION)
    assert mind.learned.HESITATE == pytest.approx(20.0 * LEARNED_INHERIT_FRACTION)


def test_traits_are_conflict_checked_and_capped() -> None:
    parent_a = _parent(SPROUT, aggression=50.0, fear=10.0, traits=(BRAVE, LOYAL))
    parent_b = _parent(SHELL, aggression=50.0, fear=10.0, traits=(TIMID,))

    for seed in range(200):
        _, mind = breed_offspring(parent_a, parent_b, random.Random(seed))
        assert len(mind.traits) <= MAX_INHERITED_TRAITS
        if BRAVE in mind.traits:
            assert TIMID not in mind.traits
        if LOYAL in mind.traits:
            assert "wild" not in mind.traits


def test_trait_pass_and_mutation_can_occur() -> None:
    parent_a = _parent(SPROUT, aggression=50.0, fear=10.0, traits=(BRAVE,))
    parent_b = _parent(SHELL, aggression=50.0, fear=10.0, traits=())

    seen_with_trait = False
    seen_with_mutation = False
    for seed in range(500):
        _, mind = breed_offspring(parent_a, parent_b, random.Random(seed))
        if BRAVE in mind.traits:
            seen_with_trait = True
        if mind.traits and BRAVE not in mind.traits:
            seen_with_mutation = True
    assert seen_with_trait
    assert seen_with_mutation


def test_companion_mind_round_trip_survives_breeding() -> None:
    parent_a = _parent(SPROUT, aggression=55.0, fear=25.0, traits=(BRAVE,))
    parent_b = _parent(SHELL, aggression=35.0, fear=45.0, traits=(TIMID,), learn_defend=16.0)

    _, mind = breed_offspring(parent_a, parent_b, random.Random(12))
    restored = companion_mind_from_dict(companion_mind_to_dict(mind))

    assert restored == mind
