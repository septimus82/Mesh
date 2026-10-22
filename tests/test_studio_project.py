from __future__ import annotations

import json

import pytest

from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.fast


def _starter(tmp_path):
    root = tmp_path / "game"
    create_project(root, "Game", template_id="starter")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project.open(root, config.get("world_file"))
    assert project is not None
    return root, project


def _person(root):
    return next(p for p in json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8")) if p["id"] == "person")


def test_open_returns_none_without_a_world(tmp_path) -> None:
    assert Project.open(tmp_path, None) is None
    assert Project.open(tmp_path, "worlds/missing.json") is None


def test_edits_undo_redo_and_dirty_tracking(tmp_path) -> None:
    root, project = _starter(tmp_path)
    assert not project.is_dirty and not project.can_undo()
    before = len(ops.entities(project.scene()))
    project.edit_scene(lambda s: ops.place_prefab(s, project.current, _person(root), 400, 300)[0])
    assert len(ops.entities(project.scene())) == before + 1 and project.is_dirty
    assert project.undo() and len(ops.entities(project.scene())) == before
    assert project.redo() and len(ops.entities(project.scene())) == before + 1
    with pytest.raises(ops.OpError):
        project.edit_scene(lambda s: ops.rename_entity(s, "nope", "X"))
    assert len(ops.entities(project.scene())) == before + 1  # a rejected edit changes nothing


def test_rooms_doors_save_and_reopen(tmp_path) -> None:
    root, project = _starter(tmp_path)
    start = project.current
    house = project.add_room("House")
    project.link_rooms(start, (400, 300), house, (200, 300))
    written = project.save()
    assert not project.is_dirty
    assert any(p.endswith("house.json") for p in written) and project.world_file in written

    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    reopened = Project.open(root, config.get("world_file"))
    assert [k for k, _, _ in reopened.rooms()] == [start, house]
    for key in (start, house):
        scene = reopened.scene(key)
        assert ops.scene_errors(scene) == []
        assert any(e.get("tag") == "door" for e in ops.entities(scene))
    assert any(e.get("tag") == "player" for e in ops.entities(reopened.scene(house)))


def test_undo_of_add_room_unregisters_it(tmp_path) -> None:
    _, project = _starter(tmp_path)
    project.add_room("Cellar")
    assert "cellar" in project.world["scenes"]
    project.undo()
    assert "cellar" not in project.world["scenes"]
    assert "cellar" not in project.scenes
