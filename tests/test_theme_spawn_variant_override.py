from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock


def _make_controller():
    from engine.prefabs import get_prefab_manager
    from engine.scene_controller import SceneController

    class _StubController(SceneController):
        def __init__(self) -> None:
            self.window = MagicMock()
            self.window.engine_config = MagicMock()
            self.window.engine_config.encounter_budget_profiles = {"easy": 0.8, "normal": 1.0, "hard": 1.25}
            self.current_scene_path = "scenes/test_scene.json"
            self.layers = {}
            self._loaded_scene_data = {}
            get_prefab_manager().load()

    return _StubController()


def test_theme_spawn_variant_override_applies_only_to_placeholders() -> None:
    from engine.encounter_cost import is_mini_boss_payload
    from engine.prefabs import get_prefab_manager

    controller = _make_controller()
    scene_data = {
        "settings": {
            "use_theme_spawns": True,
            "encounter_budget": 10,
            "encounter_budget_profile": "easy",
            "encounter_seed": 1,
            "allow_mini_bosses": True,
            "theme_spawn_variant_id": "mini_boss",
        },
        "entities": [
            {"id": "placeholder", "prefab_id": "theme_enemy_placeholder", "x": 100, "y": 100, "behaviours": ["EnemyAI"]},
            {"id": "normal_enemy", "prefab_id": "slime_blob", "x": 200, "y": 100, "behaviours": ["EnemyAI"]},
        ],
    }
    encounter_set = SimpleNamespace(enemy_prefab_ids=["slime_blob"], drop_table_id=None, variant_id=None)
    theme = SimpleNamespace(default_variant_id=None)

    controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    placeholder = next(e for e in scene_data["entities"] if e.get("id") == "placeholder")
    assert placeholder["prefab_id"] == "slime_blob"
    assert placeholder["variant_id"] == "mini_boss"

    payload = get_prefab_manager().resolve_with_variant(placeholder["prefab_id"], placeholder["variant_id"])
    assert is_mini_boss_payload(payload) is True

    normal = next(e for e in scene_data["entities"] if e.get("id") == "normal_enemy")
    assert "variant_id" not in normal


def test_theme_spawn_variant_override_candidate_variant_takes_precedence() -> None:
    from engine.encounter_cost import is_elite_payload, is_mini_boss_payload
    from engine.prefabs import get_prefab_manager

    controller = _make_controller()
    scene_data = {
        "settings": {
            "use_theme_spawns": True,
            "encounter_budget": 10,
            "encounter_budget_profile": "easy",
            "encounter_seed": 1,
            "allow_mini_bosses": True,
            "theme_spawn_variant_id": "mini_boss",
        },
        "entities": [
            {"id": "placeholder", "prefab_id": "theme_enemy_placeholder", "x": 100, "y": 100, "behaviours": ["EnemyAI"]},
        ],
    }
    encounter_set = SimpleNamespace(
        enemy_prefab_ids=[{"prefab_id": "slime_blob", "variant_id": "elite"}],
        drop_table_id=None,
        variant_id=None,
    )
    theme = SimpleNamespace(default_variant_id=None)

    controller._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    placeholder = next(e for e in scene_data["entities"] if e.get("id") == "placeholder")
    assert placeholder["prefab_id"] == "slime_blob"
    assert placeholder["variant_id"] == "elite"

    payload = get_prefab_manager().resolve_with_variant(placeholder["prefab_id"], placeholder["variant_id"])
    assert is_elite_payload(payload) is True
    assert is_mini_boss_payload(payload) is False


def test_theme_spawn_variant_override_settings_validation() -> None:
    from engine.validators.theme_spawn_variant_override_validator import validate_theme_spawn_variant_override_settings

    errors, warnings = validate_theme_spawn_variant_override_settings(
        scene_path="scenes/test_scene.json",
        settings={"theme_spawn_variant_id": "mini_boss"},
    )
    assert errors == []
    assert warnings == []

    errors, warnings = validate_theme_spawn_variant_override_settings(
        scene_path="scenes/test_scene.json",
        settings={"variant_id": "mini_boss"},
    )
    assert errors == []
    assert warnings

    errors, warnings = validate_theme_spawn_variant_override_settings(
        scene_path="scenes/test_scene.json",
        settings={"theme_spawn_variant_id": "mini_boss", "variant_id": "elite"},
    )
    assert errors

    errors, warnings = validate_theme_spawn_variant_override_settings(
        scene_path="scenes/test_scene.json",
        settings={"theme_spawn_variant_id": "not_a_real_variant"},
    )
    assert errors

