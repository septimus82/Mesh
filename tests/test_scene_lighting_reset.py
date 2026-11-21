"""A scene change must not carry the last room's lighting into the next one.

Found by the capability lab (docs/reviews/milestone7_capability_lab.md): the lights an object carried
stayed behind, frozen where it was, in every later room, and a dark room's ambient darkened the next room.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.lighting import LightManager
from engine.scene_lifecycle_controller import configure_scene_lighting

pytestmark = [pytest.mark.fast]


class _Lighting:
    def __init__(self) -> None:
        self.dynamic = ["torch from the last room"]
        self.tint = None

    def clear_dynamic_lights(self) -> None:
        self.dynamic = []

    def configure_scene_lights(self, _cfg) -> None:
        pass

    def configure_scene_occluders(self, _cfg) -> None:
        pass

    def set_ambient_tint(self, tint) -> None:
        self.tint = tuple(tint)


def _window(project_ambient=(255, 255, 255, 255)):
    return SimpleNamespace(lighting=_Lighting(), engine_config=SimpleNamespace(ambient_light_rgba=project_ambient))


def test_the_last_rooms_object_lights_are_dropped() -> None:
    window = _window()
    configure_scene_lighting(window, {"entities": [], "occluders": []}, {}, "next.json")
    assert window.lighting.dynamic == []


def test_a_room_without_its_own_ambient_gets_the_projects() -> None:
    window = _window(project_ambient=(200, 210, 220, 255))
    configure_scene_lighting(window, {"occluders": []}, {"ambient_light_rgba": [25, 25, 35, 255]}, "dark.json")
    assert window.lighting.tint == (25, 25, 35, 255)
    configure_scene_lighting(window, {"occluders": []}, {}, "next.json")
    assert window.lighting.tint == (200, 210, 220, 255)


def test_clear_dynamic_lights_forgets_every_handle() -> None:
    manager = object.__new__(LightManager)
    manager._dynamic_handles = [object(), object()]
    manager.clear_dynamic_lights()
    assert manager._dynamic_handles == []
