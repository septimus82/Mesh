from __future__ import annotations

from typing import Any

from engine.console_runtime.commands import _dispatch_table
from engine.lighting import LightManager


def test_light_manager_get_lighting_stats_includes_light_counts() -> None:
    manager = object.__new__(LightManager)
    manager._last_lighting_stats = {}
    manager.shadows_mode = "none"
    manager._static_lights = [object(), object()]
    manager._dynamic_handles = [object()]
    manager._static_occluders = []

    stats = LightManager.get_lighting_stats(manager)
    assert stats["static_light_count"] == 2
    assert stats["dynamic_light_count"] == 1


def test_console_lighting_stats_includes_context_and_counts() -> None:
    class _Lighting:
        shadows_mode = "hard"

        def get_lighting_stats(self) -> dict[str, Any]:
            return {
                "shadows_mode": "hard",
                "static_light_count": 2,
                "dynamic_light_count": 1,
                "selected_shadow_light_type": "dynamic",
                "selected_shadow_light_pos": [10.0, 20.0],
                "selected_shadow_light_radius": 123.0,
                "nearest_occluder_distance_est": 5.5,
                "cull_square_intersects_any_occluder": True,
                "occluder_count": 3,
                "culled_occluder_count": 1,
                "shadow_poly_count": 5,
                "mask_rendered": True,
                "mask_backend": "fbo.use",
                "composite_ok": True,
                "fallback_drawn": False,
            }

    class _SceneController:
        current_scene_path = "scenes/test_scene.json"
        tilemap_instance = object()
        current_scene_data = {"tilemap": {"collision_layer_id": "platforms"}}

    class _Window:
        lighting = _Lighting()
        scene_controller = _SceneController()

    class _Console:
        def __init__(self) -> None:
            self.window = _Window()
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    assert "shadow_mode" in dispatch
    assert "shadows_mode" in dispatch
    assert "lighting_stats" in dispatch

    console = _Console()
    ok = dispatch["lighting_stats"](console, [])
    assert ok is True
    assert console.lines == [
        "[Lighting] scene=scenes/test_scene.json tilemap_present=True collision_layer_id=platforms shadows_mode=hard static_light_count=2 dynamic_light_count=1 selected_shadow_light_type=dynamic selected_shadow_light_pos=[10.0, 20.0] selected_shadow_light_radius=123.0 nearest_occluder_distance_est=5.5 cull_square_intersects_any_occluder=True occluder_count=3 culled_occluder_count=1 shadow_poly_count=5 mask_rendered=True mask_backend=fbo.use composite_ok=True fallback_drawn=False"
    ]
