from __future__ import annotations

from collections import Counter
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _run_spawn_with_preset(preset: dict) -> list[str]:
    from engine.scene_controller import SceneController

    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 999,
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345,
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder"},
            {"prefab_id": "theme_enemy_placeholder"},
            {"prefab_id": "theme_enemy_placeholder"},
            {"prefab_id": "theme_enemy_placeholder"},
        ],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["mini_enemy", "elite_enemy", "grunt_enemy"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    pm = MagicMock()

    def get_prefab(pid: str):
        if pid == "mini_enemy":
            return {"encounter_cost": 1.0, "is_mini_boss": True}
        if pid == "elite_enemy":
            return {"encounter_cost": 1.0, "is_elite": True}
        if pid == "grunt_enemy":
            return {"encounter_cost": 1.0}
        return None

    pm.get_prefab.side_effect = get_prefab

    tm = MagicMock()

    def get_preset(preset_id: str):
        if preset_id == "normal":
            return dict(preset)
        return None

    tm.get_encounter_preset.side_effect = get_preset

    with patch("engine.scene_controller.get_prefab_manager", return_value=pm), patch(
        "engine.scene_controller.get_theme_manager", return_value=tm
    ):
        controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    return [e.get("prefab_id") for e in scene_data["entities"]]


def test_spawn_selection_is_deterministic_with_preset_caps() -> None:
    preset = {
        "id": "normal",
        "allow_elites": True,
        "elite_cap": 1,
        "allow_mini_bosses": True,
        "mini_boss_cap": 1,
    }

    out1 = _run_spawn_with_preset(preset)
    out2 = _run_spawn_with_preset(preset)
    assert out2 == out1

    counts = Counter(out1)
    assert counts["mini_enemy"] <= 1
    assert counts["elite_enemy"] <= 1


def test_spawn_selection_is_deterministic_when_preset_disables_tiers() -> None:
    preset = {
        "id": "normal",
        "allow_elites": False,
        "allow_mini_bosses": False,
        "elite_cap": 99,
        "mini_boss_cap": 99,
    }

    out1 = _run_spawn_with_preset(preset)
    out2 = _run_spawn_with_preset(preset)
    assert out2 == out1

    assert "elite_enemy" not in out1
    assert "mini_enemy" not in out1
