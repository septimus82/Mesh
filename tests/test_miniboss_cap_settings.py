from unittest.mock import MagicMock, patch


class _DeterministicRng:
    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed

    def shuffle(self, items) -> None:
        return

    def choice(self, items):
        return items[0]


@patch("engine.scene_controller.get_prefab_manager")
def test_mini_boss_separate_cap_does_not_consume_elite_cap(mock_pm) -> None:
    from engine.scene_controller import SceneController

    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 999,
            "encounter_budget_profile": "normal",
            "elite_cap": 3,
            "allow_elites": True,
            "mini_boss_cap": 1,
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
    encounter_set.enemy_prefab_ids = ["mini_enemy", "elite_enemy"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    def get_prefab(pid: str):
        if pid == "mini_enemy":
            return {"encounter_cost": 1.0, "is_mini_boss": True}
        if pid == "elite_enemy":
            return {"encounter_cost": 1.0, "is_elite": True}
        return None

    mock_pm.return_value.get_prefab.side_effect = get_prefab

    with patch("engine.scene_controller.random.Random", _DeterministicRng):
        controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    entities = scene_data["entities"]
    assert len(entities) == 4
    assert sum(1 for e in entities if e.get("prefab_id") == "mini_enemy") == 1
    assert sum(1 for e in entities if e.get("prefab_id") == "elite_enemy") == 3


@patch("engine.scene_controller.get_prefab_manager")
def test_allow_mini_bosses_false_blocks_only_mini_boss(mock_pm) -> None:
    from engine.scene_controller import SceneController

    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 999,
            "encounter_budget_profile": "normal",
            "elite_cap": 3,
            "allow_elites": True,
            "allow_mini_bosses": False,
            "encounter_seed": 12345,
        },
        "entities": [
            {"prefab_id": "theme_enemy_placeholder"},
            {"prefab_id": "theme_enemy_placeholder"},
        ],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["mini_enemy", "elite_enemy"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    def get_prefab(pid: str):
        if pid == "mini_enemy":
            return {"encounter_cost": 1.0, "is_mini_boss": True}
        if pid == "elite_enemy":
            return {"encounter_cost": 1.0, "is_elite": True}
        return None

    mock_pm.return_value.get_prefab.side_effect = get_prefab

    with patch("engine.scene_controller.random.Random", _DeterministicRng):
        controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    entities = scene_data["entities"]
    assert len(entities) == 2
    assert all(e.get("prefab_id") == "elite_enemy" for e in entities)

