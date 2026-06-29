from __future__ import annotations

import importlib
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.game_state_controller import GameStateController
from engine.monster.battle_model import BattleStats, MonsterInstance, Species
from engine.monster.collection import MONSTER_INSTANCES_KEY, MONSTER_PARTY_KEY, POCKET_BALL_COUNT_KEY, add_caught_monster
from engine.monster.progression import apply_experience, award_xp_for_victory, xp_required_for_level
from engine.save_manager import SaveManager

pytestmark = pytest.mark.fast


SPROUT = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
    types=("grass",),
    learnset=("tackle", "ember"),
    capture_rate=190,
)
SHELL = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
    capture_rate=180,
)


def test_progression_module_is_pure() -> None:
    module = importlib.import_module("engine.monster.progression")
    assert module.__name__ == "engine.monster.progression"
    assert not hasattr(module, "GameWindow")


def test_victory_xp_scales_with_opponent_level_and_species() -> None:
    low = MonsterInstance(SPROUT, level=2)
    high = MonsterInstance(SHELL, level=10)

    assert award_xp_for_victory(high) > award_xp_for_victory(low)


def test_apply_experience_levels_stats_and_learns_next_move() -> None:
    instance = MonsterInstance(
        SPROUT,
        level=4,
        known_moves=("tackle",),
        experience=xp_required_for_level(4),
    )
    before_stats = instance.stats

    result = apply_experience(instance, xp_required_for_level(5) - xp_required_for_level(4))

    assert result.instance.level == 5
    assert result.levels_gained == 1
    assert result.instance.experience == xp_required_for_level(5)
    assert result.instance.stats.hp > before_stats.hp
    assert result.instance.stats.atk >= before_stats.atk
    assert result.moves_learned == ("ember",)
    assert "ember" in result.instance.known_moves


def test_xp_level_known_moves_survive_save_manager_roundtrip(tmp_path: Path) -> None:
    window = _window_for_save()
    values = window.game_state_controller.state.values
    updated = MonsterInstance(
        SPROUT,
        level=5,
        known_moves=("tackle", "ember"),
        experience=xp_required_for_level(5),
    )
    caught = add_caught_monster(values, updated)
    values[POCKET_BALL_COUNT_KEY] = 2

    manager = SaveManager(window, save_dir=str(tmp_path))
    assert manager.save_game("slot1") is True

    fresh = _window_for_save()
    fresh_manager = SaveManager(fresh, save_dir=str(tmp_path))
    assert fresh_manager.load_game("slot1") is True
    restored = fresh.game_state_controller.state.values

    row = restored[MONSTER_INSTANCES_KEY][caught.instance_id]
    assert restored[MONSTER_PARTY_KEY] == [caught.instance_id]
    assert row["xp"] == xp_required_for_level(5)
    assert row["level"] == 5
    assert row["known_moves"] == ["tackle", "ember"]


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
