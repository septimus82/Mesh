"""#462 S2: undoing a saved room's creation, then saving, works; so does undoing past a save of a room first read by
its edit.

A save marks every undo/redo state as unsaved for what it wrote, so undo or redo past it brings those rooms back to
save again. It marked a room also in states from before the room existed: undo a saved new room, save, and Studio
looked the room up in a world without it (KeyError: Studio's Save crashed). And a room first read by an edit (the
door tool to a room not yet visited, an AI batch) was missing from the state before that edit: undo past a save then
read the room back from disk, as saved, so the undo silently didn't undo it.

Each test runs on a real project on disk and checks what is written at each step.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from engine import authoring, project_save
from engine import project_ops as ops
from engine.project_save import SaveError
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (a real project on disk, as the F3 save tests)

WORLD = "packs/core_regions/worlds/main.json"
START, CELLAR = "packs/core_regions/scenes/start.json", "packs/core_regions/scenes/cellar.json"


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("s2") / "game"
    create_project(root, "Game", template_id="blank")
    return root


@pytest.fixture()
def root(made: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(made, tmp_path / "game", copy_function=shutil.copy2))


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _tree(root: Path) -> dict[str, tuple[bytes, int]]:
    """Every file in the project, with its bytes and modification time."""
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def _changed(before: dict[str, tuple[bytes, int]], after: dict[str, tuple[bytes, int]]) -> list[str]:
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def _read(root: Path, rel: str) -> Any:
    return json.loads((root / rel).read_text(encoding="utf-8"))


def _world_rooms(root: Path) -> list[str]:
    return sorted(_read(root, WORLD)["scenes"])


def _consistent(project: Project) -> None:
    """What is to save names only rooms there are, in the state now and in every state undo or redo returns to."""
    assert project.dirty <= set(project.scenes) and project.dirty <= set(project.world["scenes"])
    for state in project._undo + project._redo:
        assert state.dirty <= set(state.world["scenes"]), (sorted(state.dirty), sorted(state.world["scenes"]))


def _named(name: str) -> Callable[[dict], dict]:
    return lambda scene: {**scene, "name": name}


def _barrel(key: str) -> Callable[[dict], dict]:
    return lambda scene: ops.place_blank(scene, key, "Barrel", 64, 64)[0]


def _add(project: Project, hd2d: bool) -> str:
    return project.add_hd2d_room("Cellar", 20, 16)[0] if hd2d else project.add_room("Cellar")


# --- the brief's sequence: new room, save, undo, save, redo, save, reopen -----------------------------------------
@pytest.mark.parametrize("hd2d", [False, True], ids=["2d", "hd2d"])
def test_a_saved_new_room_undone_saves_and_comes_back_on_redo(root: Path, hd2d: bool) -> None:
    project = _open(root)
    key = _add(project, hd2d)
    project.edit_scene(_barrel(key), key)
    project.save()
    saved = _tree(root)
    map_rel = project.map_path(key)
    assert CELLAR in saved and map_rel in saved and _world_rooms(root) == ["cellar", "start"]

    assert project.undo() and project.undo()  # (the barrel, then the room)
    assert "cellar" not in project.world["scenes"] and project.is_dirty
    _consistent(project)
    assert project.save() == [WORLD]  # was: KeyError 'cellar'
    after_undo = _tree(root)
    assert _changed(saved, after_undo) == [WORLD]  # the room's own files are left as they are (S4 owns them)
    assert _world_rooms(root) == ["start"] and not project.is_dirty
    _consistent(project)
    assert project.save() == [] and _tree(root) == after_undo  # saving again writes nothing

    assert project.redo() and project.redo()
    # the world is to save, and the room again (no room's file since the last save: it may have gone meanwhile)
    assert project.is_dirty and project.dirty == {key} and project.world_dirty
    _consistent(project)
    assert sorted(project.save()) == sorted([CELLAR, WORLD])
    assert _world_rooms(root) == ["cellar", "start"]
    assert (root / CELLAR).read_bytes() == saved[CELLAR][0] and _tree(root)[map_rel] == saved[map_rel]

    reopened = _open(root)
    assert [e.get("name") for e in ops.entities(reopened.scene(key))].count("Barrel") == 1
    assert reopened.map_path(key) == map_rel


def test_a_saved_room_undone_whose_file_is_removed_meanwhile_is_written_again_on_redo(root: Path) -> None:
    """Found in review: its file, no room's once the room was undone and saved, removed by hand (or a later cleanup);
    redo and save must write the room again, never a world naming a room with no file."""
    project = _open(root)
    key = project.add_room("Cellar")
    project.edit_scene(_barrel(key), key)
    project.save()
    assert project.undo() and project.undo()
    project.save()
    (root / CELLAR).unlink()
    assert project.redo() and project.redo()
    assert sorted(project.save()) == sorted([CELLAR, WORLD])
    assert [e.get("name") for e in ops.entities(_open(root).scene(key))].count("Barrel") == 1


@pytest.mark.parametrize("hd2d", [False, True], ids=["2d", "hd2d"])
def test_a_room_undone_after_a_later_edit_was_saved_saves_its_older_content_on_redo(root: Path, hd2d: bool) -> None:
    """Undo past the save of the room's edit as well as its creation: redo brings the room back as it was before
    the edit, which differs from its file, so that is saved."""
    project = _open(root)
    key = _add(project, hd2d)
    project.save()
    first = _read(root, CELLAR)
    project.edit_scene(_named("Wine cellar"), key)
    project.save()
    assert project.undo() and project.undo()
    assert project.save() == [WORLD] and _world_rooms(root) == ["start"]
    assert project.redo()  # the room, before its edit
    assert project.dirty == {key} and project.scene(key)["name"] != "Wine cellar"
    assert sorted(project.save()) == sorted([CELLAR, WORLD])
    assert _read(root, CELLAR) == first
    assert project.redo() and project.dirty == {key}
    project.save()
    assert _read(root, CELLAR)["name"] == "Wine cellar" and _world_rooms(root) == ["cellar", "start"]


def test_an_unsaved_new_room_undone_then_saved_and_redone(root: Path) -> None:
    project = _open(root)
    before = _tree(root)
    key = project.add_room("Cellar")
    map_rel = project.map_path(key)
    assert project.undo()
    _consistent(project)
    assert not project.is_dirty and project.save() == []
    assert _changed(before, _tree(root)) == [map_rel]  # (the map file written when the room was added: S4)
    assert project.redo() and project.dirty == {key} and project.world_dirty
    assert sorted(project.save()) == sorted([CELLAR, WORLD])
    assert _world_rooms(root) == ["cellar", "start"]


def test_an_existing_room_edited_saved_undone_and_saved_is_back_on_disk(root: Path) -> None:
    project = _open(root)
    original = _read(root, START)
    project.edit_scene(_named("Changed"), "start")
    project.save()
    assert project.undo()
    assert project.save() == [START] and _read(root, START) == original
    assert project.redo() and project.save() == [START] and _read(root, START)["name"] == "Changed"


def test_other_rooms_changes_stay_when_a_new_room_is_undone(root: Path) -> None:
    project = _open(root)
    project.edit_scene(_named("Hall"), "start")
    project.add_room("Cellar")
    project.save()
    hall = (root / START).read_bytes()
    assert project.undo()  # only the room
    # (the start room is written again, as it is: a save marks the states before it unsaved for all it wrote)
    assert sorted(project.save()) == sorted([START, WORLD])
    assert (root / START).read_bytes() == hall and _world_rooms(root) == ["start"]
    assert _open(root).scene("start")["name"] == "Hall"


# --- a room first read by the edit being undone -------------------------------------------------------------------
@pytest.fixture()
def attic(root: Path) -> tuple[Path, str, Any]:
    """The project with a second room, Attic, saved; reopened, so only the start room is read."""
    project = _open(root)
    key = project.add_room("Attic")
    project.save()
    return root, key, _read(root, project.path(key))


def test_undo_past_a_save_restores_a_room_first_read_by_its_edit(attic: tuple[Path, str, Any]) -> None:
    root, key, original = attic
    project = _open(root)
    assert key not in project.scenes
    project.edit_scene(_named("Renamed"), key)
    project.save()
    assert project.undo()
    assert project.scene(key)["name"] == original["name"] == "Attic"  # was: the edit, read back from disk
    _consistent(project)
    path = project.path(key)
    assert project.save() == [path] and _read(root, path) == original
    assert project.redo() and project.save() == [path] and _read(root, path)["name"] == "Renamed"


def test_undo_past_a_save_without_reading_the_room_first_saves_it(attic: tuple[Path, str, Any]) -> None:
    root, key, original = attic
    project = _open(root)
    project.edit_scene(_named("Renamed"), key)
    project.save()
    assert project.undo()
    path = project.path(key)
    assert project.save() == [path]  # was: KeyError (the room missing from the state undone to)
    assert _read(root, path) == original


def test_the_door_tool_to_a_room_not_visited_yet_undoes_past_a_save(attic: tuple[Path, str, Any]) -> None:
    root, key, original = attic
    project = _open(root)
    start = _read(root, START)
    project.link_rooms("start", (96, 96), key, (64, 64))
    project.save()
    assert project.undo()
    assert sorted(project.save()) == sorted([START, project.path(key)])
    assert _read(root, START) == start and _read(root, project.path(key)) == original


def test_an_ai_batch_reading_a_room_first_undoes_past_a_save(attic: tuple[Path, str, Any]) -> None:
    root, key, original = attic
    project = _open(root)
    authoring.apply(project, [{"op": "place_blank", "room": key, "name": "Crate", "x": 32, "y": 32}])
    project.save()
    assert project.undo()
    assert project.save() == [project.path(key)] and _read(root, project.path(key)) == original


# --- AI/MCP: a room made by a batch -------------------------------------------------------------------------------
def test_a_room_made_by_an_ai_batch_undone_after_save_and_redone(root: Path) -> None:
    project = _open(root)
    out = authoring.apply(project, [{"op": "add_room", "label": "Cellar"},
                                    {"op": "place_blank", "room": "cellar", "name": "Crate", "x": 32, "y": 32}])
    assert out["ok"]
    project.save()
    saved = _tree(root)
    assert project.undo()
    assert project.save() == [WORLD] and _world_rooms(root) == ["start"]
    assert project.redo() and sorted(project.save()) == sorted([CELLAR, WORLD])
    assert (root / CELLAR).read_bytes() == saved[CELLAR][0]
    assert "Crate" in [e.get("name") for e in ops.entities(_open(root).scene("cellar"))]


# --- a save that fails in the undone state ------------------------------------------------------------------------
def test_a_failed_save_after_undoing_a_saved_room_changes_nothing_and_can_be_retried(root: Path,
                                                                                    monkeypatch) -> None:
    project = _open(root)
    project.add_room("Cellar")
    project.save()
    assert project.undo()
    disk = _tree(root)
    memory = (sorted(project.dirty), project.world_dirty, len(project._undo), len(project._redo), project.revision)
    real = project_save._replace

    def failing(*args: Any) -> Any:
        raise OSError(28, "injected: no space", str(args[-1]))

    monkeypatch.setattr(project_save, "_replace", failing)
    with pytest.raises(SaveError):
        project.save()
    assert _tree(root) == disk
    assert (sorted(project.dirty), project.world_dirty, len(project._undo), len(project._redo),
            project.revision) == memory
    monkeypatch.setattr(project_save, "_replace", real)
    assert project.save() == [WORLD] and _world_rooms(root) == ["start"]
