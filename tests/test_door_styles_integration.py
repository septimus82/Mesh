"""Milestone 14: the three ways a door shows behave as one door.

A door picture, an invisible passage and an area over painted map art are one SceneTransition. Whichever style an AI
(through ``authoring.apply``) gives a door, it keeps the same destination and arrival spot, undoes and redoes as
one step, survives save and reopen, and goes through at run time the way its settings say.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.behaviours.scene_transition import SceneTransition
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.fast


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


@pytest.fixture
def linked(tmp_path: Path) -> tuple[Path, Project, str, str]:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    project = _open(root)
    start = project.current
    yard = project.add_room("Yard")
    authoring.apply(project, [{"op": "link_rooms", "key_a": start, "at_a": [200, 200], "key_b": yard, "at_b": [100, 100]}])
    return root, project, start, yard


def _door(project: Project, room: str) -> dict:
    return next(e for e in project.scene(room)["entities"] if e.get("tag") == "door")


def _route(door: dict) -> tuple[str, str]:
    config = door["behaviour_config"]["SceneTransition"]
    return config["target_scene"], config["spawn_id"]


@pytest.mark.parametrize("style", ["passage", "map_art", "door"])
def test_every_style_keeps_the_route_undoes_saves_and_reopens(linked, style: str) -> None:
    root, project, start, yard = linked
    door_id, route = _door(project, start)["id"], _route(_door(project, start))
    assert route == (yard, f"from_{start}")
    first = "map_art" if style == "door" else "door"  # "door" is the default: arrive at it from another style
    authoring.apply(project, [{"op": "set_door", "room": start, "entity_id": door_id, "style": first}])
    before = project.scene(start)

    authoring.apply(project, [{"op": "set_door", "room": start, "entity_id": door_id, "style": style,
                               "touch": False, "interact": True}])
    door = _door(project, start)
    assert ops.door_style(door) == style and _route(door) == route, "a style changes how it shows, not where it goes"
    assert ops.door_settings(door)["interact"] and not ops.door_settings(door)["touch"]
    assert bool(door.get("picture_hidden")) == (style != "door") and door["sprite"] == ops.DOOR_SPRITE
    assert not ops.has_ground_shadow(door) and not ops.casts_shadow(door)
    after = project.scene(start)

    assert project.undo() and project.scene(start) == before, "one batch, one undo step"
    assert project.redo() and project.scene(start) == after
    project.save()
    reopened = _door(_open(root), start)
    assert reopened == door, "save and reopen keep the style, the hidden picture, the area and the route"


def test_the_ai_sees_set_door_with_its_settings() -> None:
    described = {d["op"]: d for d in authoring.describe()}
    params = {p["name"] for p in described["set_door"]["params"]}
    assert {"entity_id", "style", "width", "height", "touch", "interact"} <= params


def test_a_refused_style_changes_nothing(linked) -> None:
    _root, project, start, _yard = linked
    before = project.all_documents()
    with pytest.raises(authoring.ChangeError, match="shows as one of"):
        authoring.apply(project, [{"op": "set_door", "room": start, "entity_id": _door(project, start)["id"],
                                   "style": "portal"}])
    assert project.all_documents() == before


class _Feet:
    def __init__(self, x: float, y: float) -> None:
        self.mesh_tag, self.mesh_name = "player", "Hero"
        self.left, self.right, self.bottom, self.top = x - 10, x + 10, y - 20, y + 20


def _runtime(door: dict, player: _Feet) -> tuple[SceneTransition, MagicMock]:
    """The saved door as the game builds it, one frame run with the player standing at ``player``."""
    entity = MagicMock(mesh_name=door["name"], center_x=door["x"], center_y=door["y"], mesh_entity_data=door)
    window = MagicMock()
    window.get_flag = lambda name, default=False: default
    window.scene_controller = SimpleNamespace(all_sprites=[player])
    behaviour = SceneTransition(entity, window, **door["behaviour_config"]["SceneTransition"])
    behaviour.update(1 / 60)
    return behaviour, window


@pytest.mark.parametrize("style", ["passage", "map_art"])
def test_a_hidden_door_goes_through_by_its_area_to_the_same_place(linked, style: str) -> None:
    root, project, start, yard = linked
    door_id = _door(project, start)["id"]
    authoring.apply(project, [{"op": "set_door", "room": start, "entity_id": door_id, "style": style}])
    project.save()
    door = _door(_open(root), start)
    half_w = ops.door_settings(door)["width"] / 2

    _, away = _runtime(door, _Feet(door["x"] + half_w + 40, door["y"]))
    away.request_scene_change.assert_not_called()
    _, inside = _runtime(door, _Feet(door["x"] + half_w - 2, door["y"]))
    inside.request_scene_change.assert_called_once_with(yard)
    inside.set_next_spawn_point.assert_called_once_with(f"from_{start}")


def test_a_door_set_to_press_e_waits_for_e(linked) -> None:
    _root, project, start, yard = linked
    door_id = _door(project, start)["id"]
    authoring.apply(project, [{"op": "set_door", "room": start, "entity_id": door_id, "style": "passage",
                               "touch": False, "interact": True}])
    door = _door(project, start)
    behaviour, window = _runtime(door, _Feet(door["x"], door["y"]))
    window.request_scene_change.assert_not_called()  # standing in it does nothing
    behaviour.on_interact(window, _Feet(door["x"], door["y"]))
    window.request_scene_change.assert_called_once_with(yard)
