"""Milestone 23D: the room a new game starts in, and a room's music, as Studio sets them (``project_ops`` and the
Studio project): the world's start room by the game's own rules, set in one undo step (before and after Save), and
the three music states (carry on, silence, a track) kept apart through saving and reopening; music imported into
assets/music without replacing a file already there."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import project_ops as ops
from engine.studio_project import Project

pytestmark = pytest.mark.fast

WORLD = "worlds/main.json"


def _project(root: Path, *, world_extra: dict | None = None, music: dict[str, object] | None = None) -> Project:
    """Village (start), Woodland and Ruins; ``music``: a room's ``settings.music`` as written (absent: none)."""
    scenes = {}
    for key in ("village", "woodland", "ruins"):
        settings: dict = {}
        if music and key in music:
            settings["music"] = music[key]
        (root / "scenes").mkdir(parents=True, exist_ok=True)
        (root / "scenes" / f"{key}.json").write_text(json.dumps({"entities": [], "settings": settings}), encoding="utf-8")
        scenes[key] = {"label": key.capitalize(), "path": f"scenes/{key}.json"}
    world = {"id": "main", "start_scene": "village", "scenes": scenes, **(world_extra or {})}
    (root / "worlds").mkdir(exist_ok=True)
    (root / WORLD).write_text(json.dumps(world), encoding="utf-8")
    return Project(root, WORLD)


def _saved_world(root: Path) -> dict:
    world: dict = json.loads((root / WORLD).read_text(encoding="utf-8"))
    return world


def test_the_start_room_is_found_as_the_game_finds_it() -> None:
    scenes = {"a": {"path": "a.json"}, "b": {"path": "b.json", "tags": ["start"]}}
    assert ops.start_room({"start_scene": "a", "scenes": scenes}) == "a"
    assert ops.start_room({"initial_scene_key": "a", "scenes": scenes}) == "a"  # (an older world's key)
    assert ops.start_room({"scenes": scenes}) == "b"  # (tagged "start")
    assert ops.start_room({"start_scene": "gone", "scenes": scenes}) is None  # (the game: its config's scene)
    assert ops.start_room({"scenes": {"a": {"path": "a.json"}}}) is None


def test_setting_the_start_room_changes_only_start_scene_and_refuses_a_room_that_isnt_there() -> None:
    world = {"id": "w", "start_scene": "a", "initial_scene_key": "a", "scenes": {"a": {"path": "a.json"},
                                                                                "b": {"path": "b.json"}}}
    out = ops.set_start_room(world, "b")
    assert out == {**world, "start_scene": "b"} and world["start_scene"] == "a"  # (a copy; the rest as it was)
    for bad in ("c", "", None, 3):
        with pytest.raises(ops.OpError, match="no room"):
            ops.set_start_room(world, bad)


def test_one_undo_step_dirty_and_saved_and_undo_redo_before_and_after_save(tmp_path: Path) -> None:
    project = _project(tmp_path)
    project.current = "ruins"  # (the room being edited)
    project.set_start_room("woodland")
    assert project.world_dirty and project.is_dirty and project.start_key() == "woodland"
    assert project.current == "ruins" and [k for k, _l, _p in project.rooms()][0] == "woodland"
    assert project.undo() and project.start_key() == "village" and project.redo() and project.start_key() == "woodland"
    assert "worlds/main.json" in project.save() and not project.is_dirty
    assert _saved_world(tmp_path)["start_scene"] == "woodland"
    assert project.undo() and project.start_key() == "village" and project.world_dirty  # (after Save: to save again)
    project.save()
    assert _saved_world(tmp_path)["start_scene"] == "village"
    assert project.redo() and project.world_dirty and project.save()
    assert Project(tmp_path, WORLD).start_key() == "woodland"  # (reopened)
    with pytest.raises(ops.OpError):
        project.set_start_room("cellar")
    assert project.start_key() == "woodland" and not project.is_dirty


def test_an_older_world_naming_no_room_of_its_own_opens_untouched(tmp_path: Path) -> None:
    project = _project(tmp_path, world_extra={"start_scene": "cellar"})
    before = (tmp_path / WORLD).read_bytes()
    assert project.start_key() == project.rooms()[0][0] and project.current == project.start_key()
    assert not project.is_dirty and project.save() == [] and (tmp_path / WORLD).read_bytes() == before


def test_three_music_states_kept_apart_through_save_and_reopen(tmp_path: Path) -> None:
    project = _project(tmp_path, music={"ruins": None})  # (an older room storing "music": null)
    assert ops.room_music(project.scene("ruins")) == {"mode": "silence", "path": ""}
    assert ops.room_music(project.scene("woodland")) == {"mode": "continue", "path": ""}
    project.edit_scene(lambda s: ops.set_room_music(s, "track", r"assets\music\theme_a.wav"), "village")
    project.edit_scene(lambda s: ops.set_room_music(s, "track", "assets/music/x.ogg"), "woodland")
    project.edit_scene(lambda s: ops.set_room_music(s, "continue"), "woodland")
    project.edit_scene(lambda s: ops.set_room_music(s, "silence"), "ruins")  # (the same again: still null)
    project.save()
    rooms = {k: json.loads((tmp_path / "scenes" / f"{k}.json").read_text(encoding="utf-8"))["settings"]
             for k in ("village", "woodland", "ruins")}
    assert rooms == {"village": {"music": "assets/music/theme_a.wav"}, "woodland": {}, "ruins": {"music": None}}
    again = Project(tmp_path, WORLD)
    assert [ops.room_music(again.scene(k))["mode"] for k in ("village", "woodland", "ruins")] == \
        ["track", "continue", "silence"]
    again.edit_scene(lambda s: ops.set_room_music(s, "silence"), "woodland")
    assert again.undo() and "music" not in again.scene("woodland")["settings"]  # (undone: no setting, not null)
    assert again.redo() and again.scene("woodland")["settings"] == {"music": None}


@pytest.mark.parametrize("mode, path", [("loud", ""), ("track", ""), ("track", "C:/music/a.ogg"),
                                        ("track", "../a.ogg"), ("track", "assets/music/a.txt")])
def test_music_choices_the_game_cant_use_are_refused(mode: str, path: str) -> None:
    with pytest.raises(ops.OpError):
        ops.set_room_music({"settings": {}}, mode, path)


def test_music_imported_into_assets_music_never_replaces_a_file_already_there(tmp_path: Path) -> None:
    project = _project(tmp_path / "game")
    source = Path(__file__).resolve().parents[1] / "assets" / "music" / "forest_theme.wav"
    first = project.import_sound(source, "music")
    assert first == "assets/music/forest_theme.wav" and project.import_sound(source, "music") == first  # (same bytes)
    other = tmp_path / "elsewhere" / "forest_theme.wav"
    other.parent.mkdir()
    other.write_bytes((Path(__file__).resolve().parents[1] / "assets" / "music" / "dungeon_theme.wav").read_bytes())
    assert project.import_sound(other, "music") == "assets/music/forest_theme_2.wav"
    assert (tmp_path / "game" / first).read_bytes() == source.read_bytes()  # (the first untouched)
    assert project.music_files()[:2] == ["assets/music/forest_theme.wav", "assets/music/forest_theme_2.wav"]
    assert project.import_sound(source) == "assets/ambience/forest_theme.wav"  # (a sound: as before)
