from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


def test_encounter_resolution_methods_are_bound_from_part_module() -> None:
    from engine.scene_controller import SceneController

    for name in (
        "_apply_theme_runtime",
        "_resolve_legacy_spawns",
        "_resolve_budgeted_spawns",
    ):
        method = getattr(SceneController, name, None)
        assert callable(method), f"SceneController.{name} missing or not callable"
        assert getattr(method, "__module__", None) == "engine.scene_controller_parts.encounter_resolution"


def test_apply_theme_runtime_still_routes_to_bound_budget_resolver() -> None:
    from engine.scene_controller import SceneController

    controller = object.__new__(SceneController)
    calls: list[tuple[dict[str, Any], Any, Any]] = []

    class _EncounterSet:
        ambient_audio_key = None
        enemy_prefab_ids = ["slime"]

    class _Theme:
        lighting_hint = None

    class _ThemeManager:
        def get_theme(self, theme_id: str) -> Any:
            assert theme_id == "moss"
            return _Theme()

        def get_encounter_set(self, _encounter_set_id: str) -> Any:
            raise AssertionError("explicit encounter_set_id should not be used")

        def resolve_encounter_set_for_theme(self, theme_id: str) -> Any:
            assert theme_id == "moss"
            return _EncounterSet()

    import engine.scene_controller as scene_controller_module

    original_get_theme_manager = scene_controller_module.get_theme_manager
    try:
        scene_controller_module.get_theme_manager = lambda: _ThemeManager()
        controller._resolve_budgeted_spawns = lambda scene_data, encounter_set, theme: calls.append((scene_data, encounter_set, theme))
        scene_data = {"settings": {"region_theme": "moss", "use_theme_spawns": True}, "entities": []}

        controller._apply_theme_runtime(scene_data)
    finally:
        scene_controller_module.get_theme_manager = original_get_theme_manager

    assert len(calls) == 1
    assert calls[0][0] is scene_data
