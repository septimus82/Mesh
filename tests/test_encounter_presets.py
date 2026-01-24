from unittest.mock import MagicMock, patch


class _DeterministicRng:
    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed

    def shuffle(self, items) -> None:
        return

    def choice(self, items):
        return items[0]


@patch("engine.scene_controller.get_prefab_manager")
def test_preset_by_difficulty_applies_when_present(mock_pm) -> None:
    from engine.scene_controller import SceneController

    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 20,
            "encounter_budget_profile": "normal",
            "encounter_seed": 12345,
        },
        "entities": [{"prefab_id": "theme_enemy_placeholder"}],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["elite_enemy"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    mock_pm.return_value.get_prefab.return_value = {"encounter_cost": 1.0, "is_elite": True}

    tm = MagicMock()
    tm.get_encounter_preset.return_value = {"id": "normal", "allow_elites": False}

    with patch("engine.scene_controller.get_theme_manager", return_value=tm), patch(
        "engine.scene_controller.random.Random", _DeterministicRng
    ):
        controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    assert scene_data["entities"] == []


@patch("engine.scene_controller.get_prefab_manager")
def test_explicit_scene_override_beats_preset(mock_pm) -> None:
    from engine.scene_controller import SceneController

    window = MagicMock()
    window.engine_config.encounter_budget_profiles = {"normal": 1.0}
    controller = SceneController(window)
    controller.current_scene_path = "scenes/test.json"

    scene_data = {
        "settings": {
            "encounter_budget": 20,
            "encounter_budget_profile": "normal",
            "allow_elites": True,
            "encounter_seed": 12345,
        },
        "entities": [{"prefab_id": "theme_enemy_placeholder"}],
    }

    encounter_set = MagicMock()
    encounter_set.enemy_prefab_ids = ["elite_enemy"]
    encounter_set.variant_id = None
    encounter_set.drop_table_id = None

    theme = MagicMock()
    theme.default_variant_id = None

    mock_pm.return_value.get_prefab.return_value = {"encounter_cost": 1.0, "is_elite": True}

    tm = MagicMock()
    tm.get_encounter_preset.return_value = {"id": "normal", "allow_elites": False}

    with patch("engine.scene_controller.get_theme_manager", return_value=tm), patch(
        "engine.scene_controller.random.Random", _DeterministicRng
    ):
        controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    assert len(scene_data["entities"]) == 1
    assert scene_data["entities"][0]["prefab_id"] == "elite_enemy"


def test_encounter_report_includes_preset_id_and_resolved_fields() -> None:
    from types import SimpleNamespace

    from engine.encounter_report import _extract_stats

    class _StubPrefabManager:
        def get_prefab(self, prefab_id: str):
            if prefab_id == "elite_enemy":
                return {"encounter_cost": 1.0, "is_elite": True}
            return None

    controller = SimpleNamespace(
        window=SimpleNamespace(engine_config=SimpleNamespace(encounter_budget_profiles={"normal": 1.0}))
    )

    scene_data = {
        "settings": {
            "encounter_budget": 20,
            "encounter_budget_profile": "normal",
        },
        "entities": [{"prefab_id": "elite_enemy"}],
    }

    tm = MagicMock()
    tm.get_encounter_preset.return_value = {"id": "normal", "elite_cap": 2, "allow_elites": False}

    import engine.encounter_report as encounter_report

    original_pm = encounter_report.get_prefab_manager
    original_tm = encounter_report.get_theme_manager
    try:
        encounter_report.get_prefab_manager = lambda: _StubPrefabManager()  # noqa: E731
        encounter_report.get_theme_manager = lambda: tm  # noqa: E731
        report = _extract_stats(scene_data, "scenes/x.json", "normal", controller)
    finally:
        encounter_report.get_prefab_manager = original_pm
        encounter_report.get_theme_manager = original_tm

    assert report.encounter_preset_id == "normal"
    assert report.elite_cap == 2
    assert report.allow_elites is False

