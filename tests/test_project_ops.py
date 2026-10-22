from __future__ import annotations

import json
import math

import pytest

from engine import project_ops as ops
from engine.scene_loader import SceneLoader, document_key

pytestmark = pytest.mark.fast

PLAYER = {
    "id": "start_player", "name": "Player", "tag": "player", "x": 128.0, "y": 128.0,
    "sprite": "assets/sprites/animated_player.png", "behaviours": ["PlayerController"],
}
PERSON_PREFAB = {
    "id": "person",
    "display_name": "Person",
    "entity": {
        "name": "Person", "tag": "npc", "sprite": "assets/sprites/animated_player.png",
        "behaviours": ["Dialogue"],
        "behaviour_config": {"Dialogue": {"dialogue": {"speaker": "Person", "start": "root", "nodes": {"root": {"text": "Hello!"}}}}},
    },
}


def _scene() -> dict:
    return {"name": "Start", "schema_version": 1, "version": 1, "entities": [dict(PLAYER)]}


def _world() -> dict:
    return {"id": "main", "start_scene": "start", "scenes": {"start": {"label": "Start", "path": "packs/core_regions/scenes/start.json"}}}


def test_place_prefab_gives_unique_ids_and_names_without_mutating_input() -> None:
    scene = _scene()
    s1, id1 = ops.place_prefab(scene, "start", PERSON_PREFAB, 300, 200)
    s2, id2 = ops.place_prefab(s1, "start", PERSON_PREFAB, 300, 200)
    assert id1 != id2
    names = [e["name"] for e in ops.entities(s2)]
    assert len(set(names)) == len(names)
    assert len(ops.entities(scene)) == 1  # pure
    assert ops.find_entity(s2, id2)["x"] == 300.0


def test_move_remove_and_rename_updates_matching_speaker() -> None:
    scene, pid = ops.place_prefab(_scene(), "start", PERSON_PREFAB, 300, 200)
    scene = ops.move_entity(scene, pid, 10, 20)
    assert (ops.find_entity(scene, pid)["x"], ops.find_entity(scene, pid)["y"]) == (10.0, 20.0)
    scene = ops.rename_entity(scene, pid, "Elder")
    entity = ops.find_entity(scene, pid)
    assert entity["name"] == "Elder"
    assert entity["behaviour_config"]["Dialogue"]["dialogue"]["speaker"] == "Elder"
    scene = ops.remove_entity(scene, pid)
    with pytest.raises(ops.OpError):
        ops.find_entity(scene, pid)
    with pytest.raises(ops.OpError):
        ops.rename_entity(scene, "start_player", "  ")


def test_add_behaviour_uses_registry_defaults_and_rejects_bad_requests() -> None:
    scene = ops.add_behaviour(_scene(), "start_player", "Health")
    entity = ops.find_entity(scene, "start_player")
    assert "Health" in ops.entity_behaviours(entity)
    fields = {f["name"]: f for f in next(b for b in ops.behaviour_catalog() if b["name"] == "Health")["fields"]}
    for name, spec in fields.items():
        if spec.get("default") is not None:
            assert entity["behaviour_config"]["Health"][name] == spec["default"]
    with pytest.raises(ops.OpError, match="already"):
        ops.add_behaviour(scene, "start_player", "Health")
    with pytest.raises(ops.OpError, match="Unknown behaviour"):
        ops.add_behaviour(scene, "start_player", "NoSuchThing")
    scene = ops.remove_behaviour(scene, "start_player", "Health")
    assert "Health" not in ops.entity_behaviours(ops.find_entity(scene, "start_player"))
    assert "Health" not in ops.find_entity(scene, "start_player").get("behaviour_config", {})


def test_set_behaviour_param_coerces_and_validates() -> None:
    scene = ops.add_behaviour(_scene(), "start_player", "Health")
    numeric = next(f for f in ops.behaviour_catalog() if f["name"] == "Health")["fields"]
    field = next(f for f in numeric if f["type"] in ("int", "float"))
    scene = ops.set_behaviour_param(scene, "start_player", "Health", field["name"], "42")
    assert ops.find_entity(scene, "start_player")["behaviour_config"]["Health"][field["name"]] == 42
    with pytest.raises(ops.OpError):
        ops.set_behaviour_param(scene, "start_player", "Health", field["name"], "lots")
    with pytest.raises(ops.OpError, match="no setting"):
        ops.set_behaviour_param(scene, "start_player", "Health", "nope", 1)


def test_dialogue_text_round_trip_and_added_when_missing() -> None:
    scene, pid = ops.place_prefab(_scene(), "start", PERSON_PREFAB, 300, 200)
    assert ops.dialogue_text(ops.find_entity(scene, pid)) == "Hello!"
    scene = ops.set_dialogue_text(scene, pid, "Hej! Åsa?")
    assert ops.dialogue_text(ops.find_entity(scene, pid)) == "Hej! Åsa?"
    scene = ops.set_dialogue_text(scene, "start_player", "I can talk too")
    player = ops.find_entity(scene, "start_player")
    assert "Dialogue" in ops.entity_behaviours(player)
    assert ops.dialogue_text(player) == "I can talk too"


def test_new_room_registers_world_and_copies_player() -> None:
    world, scene, key, path = ops.new_room(_world(), "The House", "packs/core_regions/scenes", PLAYER)
    assert key == "the_house"
    assert world["scenes"]["the_house"] == {"label": "The House", "path": "packs/core_regions/scenes/the_house.json", "tags": []}
    assert path.endswith("the_house.json")
    players = [e for e in ops.entities(scene) if e.get("tag") == "player"]
    assert len(players) == 1 and players[0]["id"] != PLAYER["id"]
    assert ops.scene_errors(scene) == []
    with pytest.raises(ops.OpError, match="already"):
        ops.new_room(world, "the house", "packs/core_regions/scenes", PLAYER)


def test_link_rooms_creates_mirrored_doors_with_arrival_spots() -> None:
    world, house, key_b, _ = ops.new_room(_world(), "House", "packs/core_regions/scenes", PLAYER)
    start, house = ops.link_rooms(_scene(), "start", "Start", (400, 300), house, key_b, "House", (200, 300))
    for scene, other_scene, other_key in ((start, house, key_b), (house, start, "start")):
        door = next(e for e in ops.entities(scene) if e.get("tag") == "door")
        config = door["behaviour_config"]["SceneTransition"]
        assert config["target_scene"] == other_key
        assert config["trigger_on_touch"] is True
        arrival = [e for e in ops.entities(other_scene) if e.get("spawn_id") == config["spawn_id"]]
        assert len(arrival) == 1, "the door's arrival spot must exist in the room it leads to"
        other_door = next(e for e in ops.entities(other_scene) if e.get("tag") == "door")
        gap = math.dist((arrival[0]["x"], arrival[0]["y"]), (other_door["x"], other_door["y"]))
        assert gap >= 64, "arriving on top of a walk-in door would bounce the player straight back"
        assert ops.scene_errors(scene) == []
    with pytest.raises(ops.OpError):
        ops.link_rooms(start, "start", "Start", (0, 0), start, "start", "Start", (0, 0))


def test_ensure_entity_ids_fills_only_missing_ids() -> None:
    scene = {"entities": [{"name": "A", "x": 1, "y": 2}, {"id": "keep", "name": "B", "x": 0, "y": 0}]}
    out = ops.ensure_entity_ids(scene, "start")
    assert out["entities"][1]["id"] == "keep"
    assert out["entities"][0]["id"]
    assert "id" not in scene["entities"][0]


def test_scene_loader_prefers_open_documents_over_disk(tmp_path, monkeypatch) -> None:
    path = tmp_path / "room.json"
    path.write_text(json.dumps({"name": "On disk", "entities": []}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    loader = SceneLoader()
    assert loader.load_scene(str(path))["name"] == "On disk"
    loader.documents[document_key(path)] = {"name": "Open in editor", "entities": []}
    assert loader.load_scene(str(path))["name"] == "Open in editor"
    unsaved = tmp_path / "not_saved_yet.json"
    loader.documents[document_key(unsaved)] = {"name": "Only in editor", "entities": []}
    assert loader.load_scene(str(unsaved))["name"] == "Only in editor"


# --- maps ----------------------------------------------------------------------------------


def test_map_file_paths_sit_next_to_the_room_in_either_separator_style() -> None:
    expected = ("packs/core_regions/maps/house.json", "../maps/house.json")
    assert ops.map_file_paths("packs/core_regions/scenes/house.json") == expected
    assert ops.map_file_paths("packs/core_regions/scenes/house.json".replace("/", chr(92))) == expected
    skeleton = ops.map_skeleton("packs/core_regions/maps/house.json", 6, 4)
    assert skeleton["tilesets"] == [{"firstgid": 1, "source": "../../../assets/tilesets/starter.json"}]
    assert [layer["name"] for layer in skeleton["layers"]] == [ops.GROUND, ops.WALLS]
    assert all(len(layer["data"]) == 24 for layer in skeleton["layers"])


def test_add_map_fills_ground_draws_border_and_validates() -> None:
    scene, map_path, skeleton = ops.add_map(_scene(), "packs/core_regions/scenes/start.json",
                                            width=6, height=4, ground=ops.STARTER_FLOOR, border=ops.STARTER_WALL)
    info = ops.map_info(scene)
    assert (info["width"], info["height"], info["tilewidth"]) == (6, 4, ops.TILE_SIZE)
    assert set(info["layers"][ops.GROUND]) == {ops.STARTER_FLOOR}
    walls = info["layers"][ops.WALLS]
    assert walls[0] == walls[5] == walls[18] == walls[23] == ops.STARTER_WALL  # corners
    assert walls[7] == 0  # interior is open
    assert scene["tilemap"]["collision_layer_id"] == ops.WALLS
    assert map_path == "packs/core_regions/maps/start.json" and skeleton["width"] == 6
    assert ops.scene_errors(scene) == []
    with pytest.raises(ops.OpError, match="already has a map"):
        ops.add_map(scene, "packs/core_regions/scenes/start.json", width=6, height=4)
    with pytest.raises(ops.OpError, match="between"):
        ops.add_map(_scene(), "packs/core_regions/scenes/start.json", width=2, height=4)


def test_paint_and_erase_cells() -> None:
    scene, _, _ = ops.add_map(_scene(), "s/scenes/a.json", width=4, height=4, ground=ops.STARTER_GRASS)
    scene = ops.paint_tiles(scene, ops.WALLS, [(0, 0), (1, 0), (9, 9)], ops.STARTER_WALL)  # (9, 9) is off the map
    walls = ops.map_info(scene)["layers"][ops.WALLS]
    assert walls[:2] == [ops.STARTER_WALL, ops.STARTER_WALL] and walls.count(ops.STARTER_WALL) == 2
    scene = ops.erase_tiles(scene, [(0, 0), (2, 0)])  # a wall is erased first; bare ground next
    info = ops.map_info(scene)
    assert info["layers"][ops.WALLS][0] == 0 and info["layers"][ops.GROUND][0] == ops.STARTER_GRASS
    assert info["layers"][ops.GROUND][2] == 0
    with pytest.raises(ops.OpError, match="no map"):
        ops.paint_tiles(_scene(), ops.GROUND, [(0, 0)], 1)


def test_cell_and_world_coordinates_round_trip() -> None:
    scene, _, _ = ops.add_map(_scene(), "s/scenes/a.json", width=10, height=5)
    info = ops.map_info(scene)
    for col, row in ((0, 0), (9, 4), (3, 2)):
        assert ops.cell_at(info, *ops.cell_center(info, col, row)) == (col, row)
    assert ops.cell_center(info, 0, 0) == (16.0, 5 * 32 - 16.0)  # row 0 is the top row
    assert ops.cell_at(info, -1, 10) is None and ops.cell_at(info, 10, 5 * 32 + 1) is None
