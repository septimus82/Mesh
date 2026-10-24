from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine import project_ops as ops
from engine.scene_lifecycle_controller import configure_scene_lighting

pytestmark = pytest.mark.fast


def _scene() -> dict:
    return {"name": "Room", "schema_version": 1, "version": 1, "entities": []}


def test_lights_are_placed_changed_duplicated_and_removed_without_touching_the_input() -> None:
    scene = _scene()
    lit, first = ops.add_light(scene, 100.4, 200, color="Cold", radius=120)
    assert "lights" not in scene and first == 0
    assert lit["lights"][0] == {"x": 100.0, "y": 200.0, "radius": 120.0, "color": "#88bbff", "mode": "soft"}
    lit = ops.set_light(lit, 0, x=50, radius=300, color=[10, 20, 30])
    assert lit["lights"][0]["x"] == 50.0 and lit["lights"][0]["radius"] == 300.0 and lit["lights"][0]["color"] == [10, 20, 30]
    lit, second = ops.duplicate_light(lit, 0)
    assert second == 1 and lit["lights"][1]["x"] == 82.0 and lit["lights"][1]["color"] == [10, 20, 30]
    lit = ops.remove_light(lit, 0)
    assert len(lit["lights"]) == 1 and lit["lights"][0]["x"] == 82.0


def test_turning_flicker_on_gives_it_a_visible_default_but_keeps_chosen_values() -> None:
    lit, _ = ops.add_light(_scene(), 0, 0)
    on = ops.set_light(lit, 0, flicker_enabled=True)["lights"][0]
    assert on["flicker_enabled"] is True and on["flicker_amount"] > 0 and on["flicker_speed"] > 0
    tuned = ops.set_light(ops.set_light(lit, 0, flicker_amount=0.5), 0, flicker_enabled=True)["lights"][0]
    assert tuned["flicker_amount"] == 0.5


def test_a_new_colour_replaces_an_older_editors_override_and_keeps_its_other_keys() -> None:
    scene = _scene()
    scene["lights"] = [{"x": 1, "y": 2, "radius": 50, "color": "#ffffff", "mode": "soft", "id": "lamp", "flicker_seed": 3}]
    light = ops.set_light(scene, 0, color="Red")["lights"][0]
    assert light["color"] == "#ff5555" and light["id"] == "lamp" and light["flicker_seed"] == 3


@pytest.mark.parametrize("change", [{"radius": 2}, {"radius": "big"}, {"color": "mauve"}, {"flicker_amount": 3}])
def test_bad_light_values_are_refused(change: dict) -> None:
    lit, _ = ops.add_light(_scene(), 0, 0)
    with pytest.raises(ops.OpError):
        ops.set_light(lit, 0, **change)


def test_a_missing_light_is_refused() -> None:
    with pytest.raises(ops.OpError):
        ops.remove_light(_scene(), 0)


def test_room_settings_are_set_and_removed_so_the_room_follows_the_project_again() -> None:
    room = ops.set_room_lighting(_scene(), enabled=True, ambient="Night", shadows="hard")
    assert room["settings"] == {"lighting_enabled": True, "lighting_ambient_color": [60, 70, 110, 255],
                                "lighting_shadows_mode": "hard"}
    back = ops.set_room_lighting(room, enabled=None, ambient=None, shadows=None)
    assert back["settings"] == {}
    with pytest.raises(ops.OpError):
        ops.set_room_lighting(_scene(), shadows="soft")


class _Lighting:
    def __init__(self) -> None:
        self.available, self.enabled = True, False
        self.base_ambient_color = (10, 10, 10, 255)
        self.ambient_color = self.base_ambient_color

    def clear_dynamic_lights(self) -> None: ...
    def configure_scene_lights(self, lights: object) -> None: ...
    def configure_scene_occluders(self, occluders: object) -> None: ...
    def set_ambient_tint(self, tint: object) -> None: ...


def test_a_rooms_own_ambient_applies_only_in_that_room() -> None:
    lighting = _Lighting()
    window = SimpleNamespace(lighting=lighting, engine_config=SimpleNamespace(lighting_enabled=False), day_night=None)
    dusk = {"lighting_enabled": True, "lighting_ambient_color": [150, 120, 140, 255]}
    configure_scene_lighting(window, {"settings": dusk}, dusk, "a.json")
    assert lighting.enabled and lighting.ambient_color == (150, 120, 140, 255)
    configure_scene_lighting(window, {"settings": {}}, {}, "b.json")
    assert not lighting.enabled and lighting.ambient_color == (10, 10, 10, 255)  # the project's, not the last room's


def test_the_day_night_clock_keeps_charge_of_the_ambient_light() -> None:
    lighting = _Lighting()
    lighting.ambient_color = (200, 180, 120, 255)
    window = SimpleNamespace(lighting=lighting, engine_config=None, day_night=SimpleNamespace(enabled=True))
    settings = {"lighting_ambient_color": [6, 6, 10]}
    configure_scene_lighting(window, {"settings": settings}, settings, "a.json")
    assert lighting.ambient_color == (200, 180, 120, 255)


def test_the_authoring_api_can_place_and_change_lights(tmp_path) -> None:  # noqa: ANN001
    import json

    from engine import authoring
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    result = authoring.apply(project, [{"op": "add_light", "x": 64, "y": 64},
                                       {"op": "set_light", "index": "@0", "color": "Red", "flicker_enabled": True},
                                       {"op": "set_room_lighting", "enabled": True, "ambient": "Cave"}])
    light = ops.lights(project.scene())[0]
    assert result["created"] == {0: 0} and light["color"] == "#ff5555" and light["flicker_enabled"] is True
    assert project.scene()["settings"]["lighting_ambient_color"] == [30, 30, 40, 255]


def test_walls_painted_in_studio_cast_shadows() -> None:
    """Studio keeps a map's layers in the scene; the wall layer must become occluders like a Tiled map's."""
    from engine.lighting.occluders import OCCLUDER_CACHE, build_occluders_from_scene_payload

    scene, _path, _doc = ops.add_map(_scene(), "packs/x/scenes/room.json", width=6, height=4)
    scene = ops.paint_tiles(scene, ops.WALLS, [(2, 1), (2, 2)], 9)
    OCCLUDER_CACHE.invalidate()
    occluders = build_occluders_from_scene_payload(scene, scene_path="studio-walls-test.json")
    assert [(o["x"], o["y"], o["width"], o["height"]) for o in occluders] == [(64.0, 32.0, 32.0, 64.0)]


def test_flicker_presets_tuning_makes_a_custom_copy_and_steady_restores_the_base() -> None:
    lit, _ = ops.add_light(_scene(), 0, 0, radius=150)
    torch = ops.set_light(lit, 0, flicker="torch")["lights"][0]
    assert torch["flicker_enabled"] is True and torch["flicker_preset"] == "torch" and ops.flicker_name(torch) == "torch"
    stronger = ops.set_light(ops.set_light(lit, 0, flicker="torch"), 0, flicker_strength=1.5)["lights"][0]
    assert stronger["flicker_preset"] == "torch" and stronger["flicker_strength"] == 1.5
    tuned = ops.set_light(ops.set_light(lit, 0, flicker="torch"), 0, flicker_reach=0.1)
    light = tuned["lights"][0]
    assert ops.flicker_name(light) == "custom" and light["flicker_reach"] == 0.1 and light["flicker_brightness"] == 0.2
    again = ops.set_light(ops.set_light(tuned, 0, flicker="candle"), 0, flicker="custom")["lights"][0]
    assert again["flicker_reach"] == 0.1, "the owner's own custom values come back"
    steady = ops.set_light(tuned, 0, flicker="steady")["lights"][0]
    assert ops.flicker_name(steady) == "steady" and steady["radius"] == 150.0
    with pytest.raises(ops.OpError):
        ops.set_light(lit, 0, flicker="strobe")


def test_shadow_fine_tuning_is_stored_and_a_softness_preset_clears_the_edge() -> None:
    room = ops.set_room_lighting(_scene(), softness="soft", edge=20, shadow_strength=0.6, quality="high",
                                 character_shadows=False)
    assert room["settings"] == {"lighting_shadow_softness": "soft", "lighting_shadow_edge": 20.0,
                                "lighting_shadow_strength": 0.6, "lighting_shadow_quality": "high",
                                "lighting_character_shadows": False}
    room = ops.set_room_lighting(room, softness="softer", character_shadows=True)
    assert "lighting_shadow_edge" not in room["settings"] and "lighting_character_shadows" not in room["settings"]
    for bad in ({"edge": 99}, {"shadow_strength": 2}, {"quality": "ultra"}):
        with pytest.raises(ops.OpError):
            ops.set_room_lighting(_scene(), **bad)


def test_shadow_fine_tuning_applies_only_in_its_room() -> None:
    lighting = _Lighting()
    window = SimpleNamespace(lighting=lighting, engine_config=None, day_night=None)
    tuned = {"lighting_shadow_edge": 12, "lighting_shadow_strength": 0.5, "lighting_shadow_quality": "low",
             "lighting_character_shadows": False}
    configure_scene_lighting(window, {"settings": tuned}, tuned, "a.json")
    assert (lighting.shadow_edge_px, lighting.shadow_strength, lighting.shadow_quality, lighting.character_shadows) \
        == (12.0, 0.5, "low", False)
    configure_scene_lighting(window, {"settings": {}}, {}, "b.json")
    assert (lighting.shadow_edge_px, lighting.shadow_strength, lighting.shadow_quality, lighting.character_shadows) \
        == (None, 1.0, "normal", True)
