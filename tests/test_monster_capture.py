from __future__ import annotations

import importlib
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.game_state_controller import GameStateController
from engine.monster.battle_model import BattleStats, MonsterInstance, Species
from engine.monster.capture import resolve_capture
from engine.monster.collection import (
    MONSTER_BOX_KEY,
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    POCKET_BALL_COUNT_KEY,
    add_caught_monster,
)
from engine.save_manager import SaveManager

pytestmark = pytest.mark.fast


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


LOW_RATE = Species(
    id="lowrate",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=10),
    types=("normal",),
    learnset=("tackle",),
    capture_rate=45,
)
HIGH_RATE = Species(
    id="highrate",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=10),
    types=("normal",),
    learnset=("tackle",),
    capture_rate=220,
)


def test_capture_module_is_pure() -> None:
    module = importlib.import_module("engine.monster.capture")
    assert module.__name__ == "engine.monster.capture"
    assert not hasattr(module, "GameWindow")


def test_capture_same_seed_inputs_are_deterministic() -> None:
    wild = MonsterInstance(HIGH_RATE, level=5, current_hp=10)

    first = resolve_capture(wild, ball_bonus=1.0, rng=_Rng(0.25))
    second = resolve_capture(wild, ball_bonus=1.0, rng=_Rng(0.25))

    assert first == second


def test_lower_hp_has_higher_capture_chance() -> None:
    full_hp = MonsterInstance(LOW_RATE, level=5)
    low_hp = MonsterInstance(LOW_RATE, level=5, current_hp=1)

    full = resolve_capture(full_hp, ball_bonus=1.0, rng=_Rng(0.0))
    low = resolve_capture(low_hp, ball_bonus=1.0, rng=_Rng(0.0))

    assert low.chance > full.chance


def test_capture_rate_affects_capture_chance() -> None:
    low_rate = MonsterInstance(LOW_RATE, level=5, current_hp=10)
    high_rate = MonsterInstance(HIGH_RATE, level=5, current_hp=10)

    low = resolve_capture(low_rate, ball_bonus=1.0, rng=_Rng(0.0))
    high = resolve_capture(high_rate, ball_bonus=1.0, rng=_Rng(0.0))

    assert high.chance > low.chance


def test_caught_monster_goes_to_party_then_box_when_party_is_full() -> None:
    values: dict[str, object] = {}
    monster = MonsterInstance(HIGH_RATE, level=5)

    first = add_caught_monster(values, monster)
    assert first.storage == "party"
    assert values[MONSTER_PARTY_KEY] == [first.instance_id]

    for _ in range(5):
        add_caught_monster(values, monster)
    overflow = add_caught_monster(values, monster)

    assert overflow.storage == "box"
    assert len(values[MONSTER_PARTY_KEY]) == 6
    assert values[MONSTER_BOX_KEY] == [overflow.instance_id]
    assert overflow.instance_id in values[MONSTER_INSTANCES_KEY]


def test_monster_collection_survives_save_manager_roundtrip(tmp_path: Path) -> None:
    window = _window_for_save()
    values = window.game_state_controller.state.values
    caught = add_caught_monster(values, MonsterInstance(HIGH_RATE, level=7, current_hp=12))
    values[POCKET_BALL_COUNT_KEY] = 2

    manager = SaveManager(window, save_dir=str(tmp_path))
    assert manager.save_game("slot1") is True
    payload = (tmp_path / "slot1.json").read_text(encoding="utf-8")
    assert "monster_party" in payload
    assert "monster_box" in payload
    assert "monster_instances" in payload
    assert "pocket_ball_count" in payload

    fresh = _window_for_save()
    fresh_manager = SaveManager(fresh, save_dir=str(tmp_path))
    assert fresh_manager.load_game("slot1") is True
    restored = fresh.game_state_controller.state.values
    assert restored[POCKET_BALL_COUNT_KEY] == 2
    assert restored[MONSTER_PARTY_KEY] == [caught.instance_id]
    assert restored[MONSTER_INSTANCES_KEY][caught.instance_id]["species_id"] == "highrate"


def _window_for_save() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.game_state_controller = GameStateController(window)
    window.scene_controller = types.SimpleNamespace(
        current_scene_path="scenes/test_scene.json",
        build_scene_snapshot=MagicMock(return_value={"entities": [], "settings": {"camera": {}}}),
    )
    window.camera_controller = types.SimpleNamespace(
        zoom_state=types.SimpleNamespace(current=1.0, target=1.0, speed=0.1, min_zoom=0.5, max_zoom=2.0),
    )
    window.request_scene_change = MagicMock()
    return window
