"""One player for the whole game (Milestone 11).

Hollowmere (the first-time creator trial) found every room holding its own copy of the player:
giving the hero a picture in the village left the house's player a placeholder. Rooms now keep only
where the player starts; the project's ``player`` prefab is the player.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_project import Project

pytestmark = pytest.mark.fast


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _player(project: Project, key: str | None = None) -> dict:
    return next(e for e in ops.entities(project.scene(key)) if e.get("tag") == "player")


@pytest.fixture()
def game(tmp_path: Path) -> Project:
    create_project(tmp_path / "game", "Game", template_id="blank")
    project = _open(tmp_path / "game")
    project.add_room("House")
    project.add_room("Cellar")
    return project


def test_every_room_shows_the_one_player(game: Project) -> None:
    keys = [key for key, _label, _path in game.rooms()]
    assert len(keys) == 3
    stored = [ops.entities(game._room(key)) for key in keys]
    assert all(any(e.get("prefab_id") == "player" and set(e) == {"id", "x", "y", "prefab_id"} for e in room) for room in stored)
    pictures = {_player(game, key)["sprite"] for key in keys}
    assert len(pictures) == 1


def test_changing_the_picture_in_one_room_changes_it_in_every_room(game: Project) -> None:
    house = next(key for key, label, _path in game.rooms() if label == "House")
    player = _player(game, house)
    game.edit_scene(lambda s: ops.set_picture(s, player["id"], "assets/sprites/hero.png"), house)
    game.edit_scene(lambda s: ops.set_look(s, player["id"], scale=2), house)
    for key, _label, _path in game.rooms():
        assert _player(game, key)["sprite"] == "assets/sprites/hero.png" and _player(game, key)["scale"] == 2
    assert game.player_dirty and game.player["sprite"] == "assets/sprites/hero.png"


def test_rooms_keep_their_own_start_position(game: Project) -> None:
    keys = [key for key, _label, _path in game.rooms()]
    player = _player(game, keys[1])
    game.edit_scene(lambda s: ops.move_entity(s, player["id"], 300, 200), keys[1])
    assert (_player(game, keys[1])["x"], _player(game, keys[1])["y"]) == (300, 200)
    assert (_player(game, keys[0])["x"], _player(game, keys[0])["y"]) != (300, 200)
    assert not game.player_dirty  # moving it is the room's business


def test_a_new_room_gets_the_player_as_it_is_now(game: Project) -> None:
    player = _player(game)
    game.edit_scene(lambda s: ops.set_collider(s, player["id"], "circle", r=10))
    attic = game.add_room("Attic")
    assert ops.collider_of(_player(game, attic))["kind"] == "circle"


def test_undo_and_redo_cover_the_player(game: Project) -> None:
    player = _player(game)
    game.edit_scene(lambda s: ops.set_picture(s, player["id"], "assets/sprites/hero.png"))
    assert game.undo() and _player(game)["sprite"] != "assets/sprites/hero.png"
    assert game.redo() and _player(game)["sprite"] == "assets/sprites/hero.png"


def test_saving_writes_the_player_and_keeps_the_other_prefabs(game: Project) -> None:
    player = _player(game)
    game.edit_scene(lambda s: ops.set_picture(s, player["id"], "assets/sprites/hero.png"))
    written = game.save()
    assert "assets/prefabs.json" in written
    prefabs = json.loads((game.root / "assets/prefabs.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in prefabs] == ["player", "person", "sign"]
    assert prefabs[0]["entity"]["sprite"] == "assets/sprites/hero.png"
    reopened = _open(game.root)
    assert all(_player(reopened, key)["sprite"] == "assets/sprites/hero.png" for key, _l, _p in reopened.rooms())


def test_the_runtime_resolves_the_room_reference(game: Project, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.paths as paths
    from engine.paths import set_content_roots
    from engine.prefabs import PrefabManager

    for name in ("_CONTENT_ROOTS", "_CONTENT_ROOTS_SIG", "_CONTENT_INDEX", "_CONTENT_INDEX_ROOTS"):
        monkeypatch.setattr(paths, name, getattr(paths, name))  # put the global roots back afterwards

    player = _player(game)
    game.edit_scene(lambda s: ops.set_picture(s, player["id"], "assets/sprites/hero.png"))
    game.save()
    set_content_roots([game.root])
    manager = PrefabManager()
    stored = next(e for e in ops.entities(game._room(game.current)) if e.get("prefab_id") == "player")
    resolved = manager.resolve(dict(stored))
    assert resolved["sprite"] == "assets/sprites/hero.png" and resolved["tag"] == "player"
    assert (resolved["x"], resolved["y"]) == (stored["x"], stored["y"])
    manager.put(ops.player_prefab_entry({**game.player, "scale": 3}))  # Studio's unsaved version
    assert manager.resolve(dict(stored))["scale"] == 3


# --- projects made before the player was shared ------------------------------------------------
def _legacy(root: Path, *, house_picture: str | None = None) -> Project:
    """A project laid out the old way: every room with its own full player."""
    create_project(root, "Old", template_id="blank")
    world_path = root / "packs/core_regions/worlds/main.json"
    start_path = root / "packs/core_regions/scenes/start.json"
    prefabs = json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8"))
    definition = next(p for p in prefabs if p["id"] == "player")["entity"]
    (root / "assets/prefabs.json").write_text(json.dumps([p for p in prefabs if p["id"] != "player"]), encoding="utf-8")
    start = json.loads(start_path.read_text(encoding="utf-8"))
    start["entities"] = [{**definition, "id": e["id"], "x": e["x"], "y": e["y"]} if e.get("prefab_id") else e
                         for e in start["entities"]]
    start_path.write_text(json.dumps(start), encoding="utf-8")
    house = {"name": "House", "schema_version": 1, "version": 1,
             "entities": [{**definition, "id": "house_player", "x": 64.0, "y": 64.0,
                           **({"sprite": house_picture} if house_picture else {})}]}
    (root / "packs/core_regions/scenes/house.json").write_text(json.dumps(house), encoding="utf-8")
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["house"] = {"label": "House", "path": "packs/core_regions/scenes/house.json", "tags": []}
    world_path.write_text(json.dumps(world), encoding="utf-8")
    return _open(root)


def test_an_old_project_with_identical_players_shares_them_losslessly(tmp_path: Path) -> None:
    project = _legacy(tmp_path / "old")
    assert set(project.own_players()) == {"start", "house"} and project.player is None
    assert project.player_differences() == {}
    assert project.share_player() == {}
    assert not project.own_players()
    assert (_player(project, "house")["x"], _player(project, "house")["y"]) == (64.0, 64.0)
    assert project.undo() and set(project.own_players()) == {"start", "house"}  # one undo step


def test_an_old_project_with_different_players_reports_what_differs(tmp_path: Path) -> None:
    project = _legacy(tmp_path / "old", house_picture="assets/sprites/ghost.png")
    assert project.player_differences() == {"house": ["picture"]}
    assert project.player_differences("house") == {"start": ["picture"]}
    replaced = project.share_player("house")  # the person chose the house's player
    assert replaced == {"start": ["picture"]}
    assert _player(project, "start")["sprite"] == "assets/sprites/ghost.png"


# --- characters collide with their feet ---------------------------------------------------------
def test_new_characters_collide_with_their_feet_whatever_their_picture(game: Project) -> None:
    player = _player(game)
    assert ops.collider_of(player)["kind"] == "box" and ops.collider_of(player)["auto"] is True
    prefabs = json.loads((game.root / "assets/prefabs.json").read_text(encoding="utf-8"))
    person = next(p for p in prefabs if p["id"] == "person")["entity"]
    assert person["components"]["collider"] == {"kind": "box", "auto": True}
    assert ops.collider_of(player, (64.0, 64.0)) == {"kind": "box", "auto": True, "w": 38, "h": 16, "offset_x": 0.0,
                                                     "offset_y": -24}


def test_an_automatic_footprint_follows_the_sprite_in_the_physics() -> None:
    """Hollowmere: a 64 px hero collided with its whole picture and couldn't fit a two-tile gap."""
    from types import SimpleNamespace

    from engine.physics_runtime import _sprite_to_aabb

    tall = SimpleNamespace(center_x=100.0, center_y=100.0, width=64.0, height=64.0,
                           mesh_entity_data={"components": {"collider": {"kind": "box", "auto": True}}})
    box = _sprite_to_aabb(tall)
    assert (box.w, box.h) == (38, 16) and box.y == 100 - 24  # the bottom quarter
    tall.width, tall.height = 32.0, 96.0  # a new picture: the feet follow it
    box = _sprite_to_aabb(tall)
    assert (box.w, box.h) == (19, 24) and box.y == 100 - 36
