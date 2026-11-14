"""#390: the saved world's rules (engine.scene_runtime.saved_world), on their own: a save's room is the room as it is
now, with what play changed; a new save leaves out what play doesn't change. The real-save checks (hidden-window
games, saves made before and after the change) are tests/test_saved_world_gpu.py."""

from __future__ import annotations

import pytest

from engine.scene_runtime.saved_world import ROOM_IDS, compose, needs_its_room, slim

pytestmark = pytest.mark.fast
ROOM_PATH = "packs/core_regions/scenes/start.json"


def _room(*ids: str, terrain: str = "new") -> dict:
    return {"name": "Start", "settings": {"hd2d": {"ground": {"terrain": terrain}}, "camera": {"zoom": {"initial": 1.0}}},
            "tilemap": {"map": "maps/start.json"}, "lights": [{"x": 1}],
            "entities": [{"id": i, "name": i, "x": 0.0, "y": 0.0} for i in ids]}


def _save(entities: list[dict], *, removed: tuple[str, ...] = (), room_ids: list[str] | None = None) -> dict:
    meta = {"scene_path": ROOM_PATH, **({ROOM_IDS: room_ids} if room_ids is not None else {})}
    return {"save_format_version": 2, "meta": meta,
            "settings": {"hd2d": {"ground": {"terrain": "old"}}, "camera": {"zoom": {"initial": 2.5}}},
            "tilemap": {"map": "maps/start.json", "overrides": {"layers": {"ground": [1, 1]}}},
            "state": {"flags": {"met": True}, "variables": {"room_memory": {ROOM_PATH: {"removed": list(removed)}}}},
            "entities": entities}


def test_an_old_save_takes_the_room_as_it_is_now_and_keeps_what_play_changed() -> None:
    save = _save([{"id": "player", "x": 99.0, "y": 50.0}, {"id": "elder", "x": 10.0, "y": 0.0},
                  {"id": "sign", "x": 0.0, "y": 0.0}, {"name": "no id", "x": 3.0, "y": 3.0}], removed=("sign",))
    room = _room("player", "elder", "sign", "newcomer")
    scene = compose(save, room, ROOM_PATH)
    assert scene["settings"]["hd2d"] == {"ground": {"terrain": "new"}}  # (the room's, not the save's copy)
    assert scene["settings"]["camera"]["zoom"] == {"initial": 2.5}  # (the save's: play changes it)
    assert scene["tilemap"] == room["tilemap"] and scene["lights"] == room["lights"]
    assert scene["state"]["flags"] == {"met": True}
    by = {e.get("id") or e.get("name"): e for e in scene["entities"]}
    assert by["player"]["x"] == 99.0 and by["elder"]["x"] == 10.0  # (as play left them)
    assert "newcomer" in by  # (added to the room since the save)
    assert "no id" in by  # (can't be matched: kept as saved)
    assert sum(1 for e in scene["entities"] if e.get("id") == "sign") == 1  # (kept in the list as it always was:
    # room memory leaves it out when the room loads; the room's copy isn't added again)
    assert room["entities"][-1]["id"] == "newcomer" and "x" in room["entities"][0]  # (the room itself untouched)


def test_a_new_save_drops_what_the_creator_deleted_and_keeps_what_play_spawned() -> None:
    save = _save([{"id": "player", "x": 5.0, "y": 5.0}, {"id": "mara", "x": 1.0, "y": 1.0},
                  {"id": "dropped_coin_7", "x": 2.0, "y": 2.0}], room_ids=["player", "mara"])
    scene = compose(save, _room("player"), ROOM_PATH)
    ids = [e.get("id") for e in scene["entities"]]
    assert ids == ["player", "dropped_coin_7"]  # (mara deleted from the room since; the coin spawned in play)


def test_a_removed_object_is_not_brought_back_by_the_room() -> None:
    scene = compose(_save([{"id": "player", "x": 0.0, "y": 0.0}], removed=("chest",), room_ids=["player", "chest"]),
                    _room("player", "chest"), ROOM_PATH)
    assert [e["id"] for e in scene["entities"]] == ["player"]


def test_slim_leaves_out_what_play_doesnt_change() -> None:
    snapshot = _save([{"id": "player", "x": 0.0, "y": 0.0}])
    snapshot["background_layers"] = [{"image": "sky.png"}]
    slim(snapshot)
    assert snapshot["settings"] == {"camera": {"zoom": {"initial": 2.5}}}
    assert not {"tilemap", "lights", "background_layers"} & set(snapshot)
    assert snapshot["entities"] and snapshot["state"]


def test_an_object_the_room_still_has_is_the_room_s_as_authored_now_where_play_left_it() -> None:
    """Dialogue, picture and behaviours edited after a save reach it; where play left the object stays the save's."""
    room = _room("player", "elder")
    room["entities"][1].update(sprite="new.png", behaviours=["Dialogue", "Wander"],
                               behaviour_config={"Dialogue": {"text": "new words"}})
    saved_elder = {"id": "elder", "x": 10.0, "y": 20.0, "elevation": 1.5, "sprite": "old.png",
                   "behaviours": [{"type": "Dialogue", "params": {"text": "old words"}}]}
    scene = compose(_save([{"id": "player", "x": 99.0, "y": 50.0}, saved_elder], room_ids=["player", "elder"]),
                    room, ROOM_PATH)
    elder = next(e for e in scene["entities"] if e["id"] == "elder")
    assert elder["sprite"] == "new.png" and elder["behaviours"] == ["Dialogue", "Wander"]
    assert elder["behaviour_config"] == {"Dialogue": {"text": "new words"}}
    assert (elder["x"], elder["y"], elder["elevation"]) == (10.0, 20.0, 1.5)
    spawned = {"id": "dropped_coin_7", "x": 2.0, "y": 2.0, "sprite": "coin.png"}
    scene = compose(_save([spawned], room_ids=["player"]), _room("player"), ROOM_PATH)
    assert spawned in scene["entities"]  # (not the room's: kept whole)


def test_only_a_save_without_its_own_room_copy_needs_its_room() -> None:
    assert needs_its_room(_save([], room_ids=["player"])) and not needs_its_room(_save([]))
