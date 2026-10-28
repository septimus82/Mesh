"""Milestone 22A.1: an expanded HD-2D room's map file (its size, tilesets and empty layers: the tiles live in the room)
kept at the room's size when Studio saves (``Project.save``), through undo and redo; a map file with tiles of its own
never resized. A real starter project on disk (integration: the fast tier stays the operations' own tests)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import engine.project_ops as ops

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def starter(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("m22a1")
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    return out / "game"


def _map_file(root: Path) -> dict:
    return json.loads((root / "packs/core_regions/maps/meadow.json").read_text(encoding="utf-8"))


def test_saving_keeps_the_map_file_at_the_rooms_size_through_undo_and_redo(starter: Path, tmp_path: Path) -> None:
    from engine.studio_project import Project

    root = tmp_path / "game"
    shutil.copytree(starter, root)
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    key, _installed = project.add_hd2d_room("Meadow", 40, 30)
    project.save()
    first = _map_file(root)
    assert (first["width"], first["height"]) == (40, 30)
    project.edit_scene(lambda s: ops.expand_hd2d_room(s, 48, 36), key)
    assert (_map_file(root)["width"], _map_file(root)["height"]) == (40, 30)  # not saved yet: the file as it was
    written = project.save()
    assert written[0] == "packs/core_regions/maps/meadow.json"  # (before the room: checked before anything is written)
    grown = _map_file(root)
    assert (grown["width"], grown["height"]) == (48, 36)
    assert all((layer["width"], layer["height"], len(layer["data"])) == (48, 36, 48 * 36) for layer in grown["layers"])
    assert grown["tilesets"] == first["tilesets"] and grown["orientation"] == "orthogonal"  # only its size changed
    project.undo()
    project.save()
    assert (_map_file(root)["width"], _map_file(root)["height"]) == (40, 30)  # undone and saved: back as it was
    project.redo()
    project.save()
    assert (_map_file(root)["width"], _map_file(root)["height"]) == (48, 36)
    room = json.loads((root / project.path(key)).read_text(encoding="utf-8"))
    assert (room["tilemap"]["width"], room["settings"]["hd2d"]["ground"]["to"]) == (48, [1536.0, 1152.0])


def test_a_map_file_with_tiles_of_its_own_is_never_resized_and_nothing_is_saved(starter: Path, tmp_path: Path) -> None:
    from engine.studio_project import Project

    root = tmp_path / "game"
    shutil.copytree(starter, root)
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    key, _installed = project.add_hd2d_room("Meadow", 40, 30)
    project.save()
    hand_made = _map_file(root)
    hand_made["layers"][0]["data"][0] = 3  # a tile drawn in the map file itself (Tiled)
    (root / "packs/core_regions/maps/meadow.json").write_text(json.dumps(hand_made), encoding="utf-8")
    room_before = (root / project.path(key)).read_bytes()
    project.edit_scene(lambda s: ops.expand_hd2d_room(s, 48, 36), key)
    with pytest.raises(ops.OpError, match="has tiles or objects of its own.*nothing was saved"):
        project.save()
    assert _map_file(root) == hand_made and (root / project.path(key)).read_bytes() == room_before
    assert key in project.dirty  # still unsaved: nothing lost


@pytest.mark.parametrize("broken", ["missing", "malformed"])
def test_a_missing_or_unreadable_map_file_refuses_the_save_and_changes_nothing(starter: Path, tmp_path: Path,
                                                                              broken: str) -> None:
    from engine.studio_project import Project

    root = tmp_path / "game"
    shutil.copytree(starter, root)
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    key, _installed = project.add_hd2d_room("Meadow", 40, 30)
    project.save()
    map_file = root / "packs/core_regions/maps/meadow.json"
    if broken == "missing":
        map_file.unlink()
    else:
        map_file.write_text("{ not json", encoding="utf-8")
    room_before = (root / project.path(key)).read_bytes()
    project.edit_scene(lambda s: ops.expand_hd2d_room(s, 48, 36), key)
    reason = "is missing" if broken == "missing" else "can't be read"
    with pytest.raises(ops.OpError, match=f"{reason}, so it can't be kept at the room's 48 x 36 tiles; nothing was saved"):
        project.save()
    assert (root / project.path(key)).read_bytes() == room_before  # the room file as it was: no sizes claimed
    assert map_file.exists() == (broken == "malformed")  # nothing made up in its place ...
    if broken == "malformed":
        assert map_file.read_text(encoding="utf-8") == "{ not json"  # ... nor written over
    assert key in project.dirty  # still unsaved: nothing lost
    project.undo()  # the size as saved: other changes save, the missing file is as it was
    project.edit_scene(lambda s: ops.set_hd2d_sun(s, preset="evening"), key)
    assert project.path(key) in project.save()


def test_undo_and_redo_across_saves_with_two_edited_rooms(starter: Path, tmp_path: Path) -> None:
    from engine.studio_project import Project

    root = tmp_path / "game"
    shutil.copytree(starter, root)
    project = Project.open(root, "packs/core_regions/worlds/main.json")
    meadow, _installed = project.add_hd2d_room("Meadow", 40, 30)
    cave, _again = project.add_hd2d_room("Cave", 16, 12, outdoor=False)
    project.save()

    def on_disk() -> tuple[list[float], str, int]:
        m = json.loads((root / project.path(meadow)).read_text(encoding="utf-8"))
        c = json.loads((root / project.path(cave)).read_text(encoding="utf-8"))
        return m["settings"]["hd2d"]["ground"]["to"], c["settings"]["hd2d"]["sun"]["color"], _map_file(root)["width"]

    project.edit_scene(lambda s: ops.expand_hd2d_room(s, 48, 36), meadow)
    project.edit_scene(lambda s: ops.set_hd2d_sun(s, preset="evening"), cave)
    project.save()
    assert on_disk() == ([1536.0, 1152.0], "#ffb070", 48)
    project.undo()  # the cave's sun
    assert cave in project.dirty
    project.save()
    assert on_disk() == ([1536.0, 1152.0], "#fff0d8", 48)
    project.undo()  # the meadow's size
    assert meadow in project.dirty
    project.save()
    assert on_disk() == ([1280.0, 960.0], "#fff0d8", 40)
    project.redo()
    project.redo()
    assert {meadow, cave} <= project.dirty
    project.save()
    assert on_disk() == ([1536.0, 1152.0], "#ffb070", 48)
    assert not project.dirty
