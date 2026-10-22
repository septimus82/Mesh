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


def test_starter_room_ships_with_a_paintable_map(tmp_path) -> None:
    root, project = _starter(tmp_path)
    info = ops.map_info(project.scene())
    assert (info["width"], info["height"]) == (24, 16)
    assert set(info["layers"][ops.GROUND]) == {ops.STARTER_GRASS}
    assert (root / "packs/core_regions/maps/start.json").is_file()
    assert (root / ops.TILESET_SOURCE).is_file()


def test_new_room_gets_floor_border_and_map_file_immediately(tmp_path) -> None:
    root, project = _starter(tmp_path)
    key = project.add_room("Cellar")
    info = ops.map_info(project.scene(key))
    assert set(info["layers"][ops.GROUND]) == {ops.STARTER_FLOOR}
    assert info["layers"][ops.WALLS][0] == ops.STARTER_WALL
    assert (root / "packs/core_regions/maps/cellar.json").is_file()  # loadable before the room is saved
    player = next(e for e in ops.entities(project.scene(key)) if e.get("tag") == "player")
    col, row = ops.cell_at(info, player["x"], player["y"])
    assert info["layers"][ops.WALLS][row * info["width"] + col] == 0  # the player doesn't start inside a wall


def test_room_without_a_map_can_get_one_and_undo_removes_it(tmp_path) -> None:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project.open(root, config.get("world_file"))
    assert ops.map_info(project.scene()) is None
    project.add_map()
    assert ops.map_info(project.scene()) is not None
    project.undo()
    assert ops.map_info(project.scene()) is None


def test_room_tilesets_list_the_starter_with_its_hints(tmp_path) -> None:
    _, project = _starter(tmp_path)
    (starter,) = project.room_tilesets()
    assert (starter["firstgid"], starter["count"], starter["columns"], starter["tile"]) == (1, 16, 8, 32)
    assert starter["hints"][ops.STARTER_WALL - 1]["layer"] == ops.WALLS


def _sixteen_px_sheet(path):
    from PIL import Image

    image = Image.new("RGBA", (48, 40), (0, 0, 0, 0))  # 3 x 2 tiles of 16 px, 8 px left over at the bottom
    image.paste((200, 30, 30, 255), (0, 0, 16, 16))
    image.paste((30, 30, 200, 128), (16, 16, 32, 32))  # half-transparent
    image.save(path)
    return path


def test_import_scales_to_map_tiles_keeps_alpha_and_reaches_every_map(tmp_path) -> None:
    from PIL import Image

    root, project = _starter(tmp_path)
    cellar = project.add_room("Cellar")
    result = project.import_tileset(_sixteen_px_sheet(tmp_path / "forest sheet.png"), 16, "Forest")
    assert result == {"name": "Forest", "source": "assets/tilesets/forest.json", "count": 6, "scaled": True}
    with Image.open(root / "assets/tilesets/forest.png") as img:
        assert img.size == (96, 64)  # 3 x 2 tiles of 32 px; the leftover strip is cut off
        assert img.getpixel((16, 16)) == (200, 30, 30, 255)
        assert img.getpixel((48, 48)) == (30, 30, 200, 128)
        assert img.getpixel((80, 16))[3] == 0
    for key in (project.current, cellar):
        names = [(t["name"], t["firstgid"]) for t in project.room_tilesets(key)]
        assert names == [("Starter", 1), ("Forest", 17)]
    again = project.import_tileset(tmp_path / "forest sheet.png", 16, "Forest")
    assert again["source"] == "assets/tilesets/forest_2.json"  # never overwrites
    later = project.add_room("Attic")
    assert [t["firstgid"] for t in project.room_tilesets(later)] == [1, 17, 23]


def test_import_rejects_what_it_cannot_use(tmp_path) -> None:
    _, project = _starter(tmp_path)
    with pytest.raises(ops.OpError, match="no file"):
        project.import_tileset(tmp_path / "missing.png", 32, "X")
    (tmp_path / "notes.png").write_text("not an image", encoding="utf-8")
    with pytest.raises(ops.OpError, match="isn't an image"):
        project.import_tileset(tmp_path / "notes.png", 32, "X")
    with pytest.raises(ops.OpError, match="smaller than one"):
        project.import_tileset(_sixteen_px_sheet(tmp_path / "small.png"), 64, "X")
