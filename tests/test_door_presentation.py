"""Milestone 12.2: one door behaviour, three ways to show it, and shadows only under things on the floor.

A door is SceneTransition. It shows as its picture, as an invisible passage, or as an area over a door painted on
the map; the hidden styles keep the picture (``picture_hidden``) so choosing the door again brings it back. Doors,
passages, arrival spots and hidden pictures get no round shadow under them unless asked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine import project_ops as ops
from engine.sprite_shadow_model import ground_shadow_default

pytestmark = pytest.mark.fast


def _rooms() -> tuple[dict, str]:
    a = {"name": "A", "schema_version": 1, "version": 1, "entities": []}
    b = {"name": "B", "schema_version": 1, "version": 1, "entities": []}
    a, _b = ops.link_rooms(a, "a", "A", (100.0, 100.0), b, "b", "B", (50.0, 50.0))
    door = next(e for e in a["entities"] if e.get("tag") == "door")
    return a, door["id"]


def _door(scene: dict, door_id: str) -> dict:
    return ops.find_entity(scene, door_id)


def test_a_new_door_is_a_picture_with_no_shadow_under_it() -> None:
    scene, door_id = _rooms()
    door = _door(scene, door_id)
    assert ops.door_style(door) == "door" and door["sprite"] == ops.DOOR_SPRITE
    assert not ops.has_ground_shadow(door) and not ops.casts_shadow(door)
    arrival = next(e for e in scene["entities"] if e.get("tag") == "spawn_point")
    assert not ops.has_ground_shadow(arrival)


def test_a_passage_hides_the_picture_keeps_it_and_works_by_an_area() -> None:
    scene, door_id = _rooms()
    passage = ops.set_door(scene, door_id, style="passage")
    door = _door(passage, door_id)
    assert door["picture_hidden"] is True and door["sprite"] == ops.DOOR_SPRITE and ops.door_style(door) == "passage"
    assert ops.door_settings(door)["width"] == 64.0 and ops.door_settings(door)["touch"] is True
    sized = _door(ops.set_door(passage, door_id, width=96, height=40), door_id)
    assert (ops.door_settings(sized)["width"], ops.door_settings(sized)["height"]) == (96.0, 40.0)
    back = _door(ops.set_door(passage, door_id, style="door"), door_id)
    assert "picture_hidden" not in back and "door_style" not in back and back["sprite"] == ops.DOOR_SPRITE
    assert ops.door_settings(back)["width"] == 0.0, "a door picture is its own area again"
    art = _door(ops.set_door(scene, door_id, style="map_art"), door_id)
    assert ops.door_style(art) == "map_art" and ops.door_settings(art)["width"] == 32.0, "one tile over the painted door"


def test_doors_refuse_what_would_break_them() -> None:
    scene, door_id = _rooms()
    with pytest.raises(ops.OpError):
        ops.set_door(scene, door_id, width=80)  # a picture is its own area
    with pytest.raises(ops.OpError):
        ops.set_door(scene, door_id, touch=False, interact=False)
    with pytest.raises(ops.OpError):
        ops.set_door(scene, door_id, style="portal")
    blank, other = ops.place_blank(scene, "a", "Rock", 10, 10)
    with pytest.raises(ops.OpError):
        ops.set_door(blank, other, style="passage")
    pressed = _door(ops.set_door(scene, door_id, touch=False, interact=True), door_id)
    assert ops.door_settings(pressed)["touch"] is False and ops.door_settings(pressed)["interact"] is True


def test_ground_shadows_by_default_only_under_things_on_the_floor() -> None:
    assert ground_shadow_default({"tag": "npc"}) and ground_shadow_default({"name": "Barrel"})
    assert not ground_shadow_default({"tag": "door"}) and not ground_shadow_default({"tag": "spawn_point"})
    assert not ground_shadow_default({"behaviours": ["SceneTransition"]})
    assert not ground_shadow_default({"behaviours": [{"type": "SceneTransition"}]}), "as the runtime holds behaviours"
    assert not ground_shadow_default({"name": "Rug", "picture_hidden": True})


def test_the_under_feet_setting_stores_only_what_differs_from_the_default() -> None:
    scene, door_id = _rooms()
    on = _door(ops.set_shadows(scene, door_id, ground=True), door_id)
    assert on["shadow_enabled"] is True and ops.has_ground_shadow(on), "asked for: a door can have one"
    assert "shadow_enabled" not in _door(ops.set_shadows(scene, door_id, ground=False), door_id)
    scene, npc_id = ops.place_blank(scene, "a", "Villager", 200, 200)
    assert "shadow_enabled" not in ops.find_entity(ops.set_shadows(scene, npc_id, ground=True), npc_id)
    assert ops.find_entity(ops.set_shadows(scene, npc_id, ground=False), npc_id)["shadow_enabled"] is False


class _Sprite:
    def __init__(self, x: float, y: float, w: float = 20, h: float = 40) -> None:
        self.mesh_tag, self.center_x, self.center_y = "player", x, y
        self.left, self.right, self.bottom, self.top = x - w / 2, x + w / 2, y - h / 2, y + h / 2


def test_a_passage_is_walked_into_by_its_area_not_its_hidden_picture() -> None:
    from engine.behaviours.scene_transition import SceneTransition

    entity = MagicMock(mesh_name="Passage", center_x=100.0, center_y=100.0, mesh_entity_data={"id": "p"})
    window = MagicMock()
    window.get_flag = lambda name, default=False: default
    behaviour = SceneTransition(entity, window, target_scene="b", trigger_on_touch=True, area_width=96, area_height=32)
    window.scene_controller = SimpleNamespace(all_sprites=[_Sprite(100.0, 160.0)])  # above the strip: outside
    behaviour.update(1 / 60)
    window.request_scene_change.assert_not_called()
    window.scene_controller = SimpleNamespace(all_sprites=[_Sprite(140.0, 125.0)])  # its feet in the strip's corner
    behaviour.update(1 / 60)
    window.request_scene_change.assert_called_once_with("b")
