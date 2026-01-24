from unittest.mock import MagicMock, patch

from engine.encounter_cost import MINI_BOSS_COST_MULT, BOSS_COST_MULT, get_effective_encounter_cost
from engine.scene_controller import SceneController


def test_miniboss_cost_mult_applies() -> None:
    base = {"encounter_cost": 10}
    mini = {"encounter_cost": 10, "is_mini_boss": True}
    mini_tag = {"encounter_cost": 10, "tags": ["mini_boss"]}
    boss = {"encounter_cost": 10, "is_boss": True}
    both = {"encounter_cost": 10, "is_boss": True, "is_mini_boss": True}

    assert get_effective_encounter_cost(base) == 10
    assert get_effective_encounter_cost(mini) == 10 * MINI_BOSS_COST_MULT
    assert get_effective_encounter_cost(mini_tag) == 10 * MINI_BOSS_COST_MULT
    assert get_effective_encounter_cost(boss) == 10 * BOSS_COST_MULT
    assert get_effective_encounter_cost(both) == 10 * BOSS_COST_MULT


@patch("engine.scene_controller.get_prefab_manager")
def test_budget_allow_elites_false_blocks_miniboss_spawns(mock_pm) -> None:
    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 20,
            "allow_elites": False,
            "encounter_seed": 12345,
        },
        "entities": [{"prefab_id": "theme_enemy_placeholder"}],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["mini_enemy"]
    encounter_set.variant_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    mock_pm.return_value.get_prefab.return_value = {"encounter_cost": 5.0, "is_mini_boss": True}

    controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    assert scene_data["entities"] == []


@patch("engine.scene_controller.get_prefab_manager")
def test_budget_elite_cap_limits_miniboss_count(mock_pm) -> None:
    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 10,
            "elite_cap": 1,
            "encounter_seed": 12345,
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder"},
            {"prefab_id": "theme_enemy_placeholder"},
            {"prefab_id": "theme_enemy_placeholder"},
        ],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["mini_enemy", "grunt_enemy"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    def get_prefab(pid: str):
        if pid == "mini_enemy":
            return {"encounter_cost": 1.0, "is_mini_boss": True}
        if pid == "grunt_enemy":
            return {"encounter_cost": 100.0}
        return None

    mock_pm.return_value.get_prefab.side_effect = get_prefab

    controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    assert len(scene_data["entities"]) == 1
    assert scene_data["entities"][0].get("prefab_id") == "mini_enemy"
    assert sum(1 for e in scene_data["entities"] if e.get("prefab_id") == "mini_enemy") == 1
