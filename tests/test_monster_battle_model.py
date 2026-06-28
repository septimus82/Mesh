from __future__ import annotations

import importlib
import random

import pytest

from engine.monster.battle_model import (
    BattleStats,
    MonsterInstance,
    Move,
    Species,
    compute_damage,
    resolve_move,
)

pytestmark = pytest.mark.fast


TYPE_CHART = {
    "fire": {"grass": 2.0, "water": 0.5},
    "grass": {"water": 2.0, "fire": 0.5},
}


SPROUT = Species(
    id="sprout",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
    types=("grass",),
    learnset=("tackle", "ember"),
)


TURTLE = Species(
    id="turtle",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)


EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)
TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)


def test_module_imports_without_runtime_initialization() -> None:
    module = importlib.import_module("engine.monster.battle_model")
    assert module.__name__ == "engine.monster.battle_model"
    assert not hasattr(module, "GameWindow")


def test_normal_effectiveness_hit_reduces_hp_by_expected_amount() -> None:
    attacker = MonsterInstance(SPROUT, level=10, known_moves=("tackle",))
    defender = MonsterInstance(TURTLE, level=10, current_hp=42)

    result = resolve_move(attacker, defender, TACKLE, TYPE_CHART, rng=None)

    expected = compute_damage(
        level=attacker.level,
        attacker_atk=attacker.stats.atk,
        defender_def=defender.stats.defense,
        move_power=TACKLE.power,
        type_mult=1.0,
        rng=None,
    )
    assert expected == 6
    assert result.damage == expected
    assert result.defender.current_hp == 42 - expected
    assert result.fainted is False


def test_type_effectiveness_changes_damage() -> None:
    attacker = MonsterInstance(SPROUT, level=10)
    grass_defender = MonsterInstance(SPROUT, level=10)
    water_defender = MonsterInstance(TURTLE, level=10)

    neutral = resolve_move(attacker, water_defender, TACKLE, TYPE_CHART, rng=None)
    super_effective = resolve_move(attacker, grass_defender, EMBER, TYPE_CHART, rng=None)
    not_very_effective = resolve_move(attacker, water_defender, EMBER, TYPE_CHART, rng=None)

    assert super_effective.type_multiplier == 2.0
    assert not_very_effective.type_multiplier == 0.5
    assert super_effective.damage > neutral.damage
    assert not_very_effective.damage < neutral.damage


def test_lethal_move_sets_fainted_and_clamps_hp_to_zero() -> None:
    attacker = MonsterInstance(SPROUT, level=50)
    defender = MonsterInstance(TURTLE, level=5, current_hp=3)

    result = resolve_move(attacker, defender, EMBER, TYPE_CHART, rng=None)

    assert result.damage >= 3
    assert result.defender.current_hp == 0
    assert result.fainted is True


def test_resolve_move_does_not_change_attacker_hp() -> None:
    attacker = MonsterInstance(SPROUT, level=10, current_hp=11)
    defender = MonsterInstance(TURTLE, level=10)

    result = resolve_move(attacker, defender, TACKLE, TYPE_CHART, rng=None)

    assert attacker.current_hp == 11
    assert result.defender.current_hp < defender.current_hp


def test_same_seeded_rng_reproduces_damage() -> None:
    attacker = MonsterInstance(SPROUT, level=10)
    defender = MonsterInstance(TURTLE, level=10)

    first = resolve_move(attacker, defender, TACKLE, TYPE_CHART, rng=random.Random(12345))
    second = resolve_move(attacker, defender, TACKLE, TYPE_CHART, rng=random.Random(12345))

    assert first == second
