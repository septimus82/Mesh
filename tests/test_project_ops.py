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
