from __future__ import annotations

import importlib

import pytest

from engine.monster.battle_model import BattleStats, MonsterInstance, Species
from engine.monster.status import POISON, apply_status, can_act, tick_end_of_turn

pytestmark = pytest.mark.fast

SPECIES = Species(
    id="testmon",
    base_stats=BattleStats(hp=40, atk=10, defense=10, spd=10),
    types=("normal",),
    learnset=("tackle",),
)


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


def test_status_module_is_pure() -> None:
    module = importlib.import_module("engine.monster.status")
    assert module.__name__ == "engine.monster.status"
    assert not hasattr(module, "GameWindow")


def test_apply_status_and_poison_end_of_turn_damage() -> None:
    instance = MonsterInstance(SPECIES, level=10, current_hp=40)
    poisoned = apply_status(instance, POISON)

    updated, events = tick_end_of_turn(poisoned)

    assert updated.current_hp == 34
    assert [event.kind for event in events] == ["poison_damage"]
    assert events[0].damage == 6


def test_sleep_blocks_action_then_wakes_after_turns() -> None:
    asleep = apply_status(MonsterInstance(SPECIES, level=10), "sleep")
    assert asleep.status_turns == 3

    may_act, events, updated = can_act(asleep, _Rng(0.99))
    assert may_act is False
    assert events[0].kind == "asleep_skip"
    assert updated.status_turns == 3

    current = asleep
    for _ in range(2):
        current, events = tick_end_of_turn(current)
        assert "woke_up" not in [event.kind for event in events]

    current, events = tick_end_of_turn(current)
    assert events[-1].kind == "woke_up"
    assert current.status_condition is None

    may_act, events, updated = can_act(current, _Rng(0.99))
    assert may_act is True
    assert events == ()


def test_poison_tick_can_faint_monster() -> None:
    poisoned = apply_status(MonsterInstance(SPECIES, level=10, current_hp=3), POISON)

    updated, events = tick_end_of_turn(poisoned)

    assert updated.fainted is True
    assert events[0].kind == "poison_damage"
