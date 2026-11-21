"""RV-2: an authored id-less prefab entity is never dropped from a save.

The room file's prefab object has no name (the prefab owns it) but the loaded entity has the prefab's name filled in,
so B-09's keys differed and every such object without a live sprite (a flag-gated one, a failed sprite) was treated as
save-only and deleted. Keys now tell a prefab object by its prefab alone. Production compose and snapshot."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine.scene_loader import SceneLoader
from engine.scene_runtime import saved_world
from engine.scene_runtime.persistence import build_scene_snapshot

ROOM = "scenes/room.json"
RAW = {"prefab_id": "ghost", "x": 5.0, "y": 5.0, "require_flags": ["night"]}  # the room file: no name
LOADED = {**RAW, "name": "Ghost", "layer": "entities"}  # after prefab resolution (engine/prefabs.py)


def _snapshot(entities: list[dict[str, Any]], counts: Any, flags: dict[str, bool]) -> dict[str, Any]:
    window = SimpleNamespace(
        camera_controller=SimpleNamespace(zoom_state=SimpleNamespace(current=1.0, target=1.0, speed=5.0, min_zoom=0.5,
                                                                     max_zoom=2.0)),
        game_state=SimpleNamespace(snapshot=lambda: {}), scene_loader=SceneLoader(),
        get_flag=lambda f, d=False: flags.get(f, d))
    controller = SimpleNamespace(window=window, _loaded_scene_source_data={"entities": copy.deepcopy(entities)},
                                 all_sprites=[], layers={}, tilemap_instance=None, _room_idless=counts)
    return build_scene_snapshot(cast(Any, controller))


@pytest.mark.fast
def test_an_authored_idless_prefab_object_without_a_sprite_is_kept() -> None:
    counts = saved_world.room_idless([RAW])
    flags = {"night": False}
    assert len(_snapshot([LOADED], counts, flags)["entities"]) == 1
    flags["night"] = True  # the gate passes in play; no sprite until the room reloads
    assert [e["prefab_id"] for e in _snapshot([LOADED], counts, flags)["entities"]] == ["ghost"]


@pytest.mark.fast
def test_the_flag_gated_prefab_object_survives_save_and_load_round_trips() -> None:
    room = {"entities": [dict(RAW)]}
    entities = [dict(LOADED)]
    flags = {"night": True}
    for _ in range(3):
        save = _snapshot(entities, saved_world.room_idless(room["entities"]), flags)
        assert [e["prefab_id"] for e in save["entities"]] == ["ghost"]
        loaded = saved_world.compose(save, room, ROOM)
        assert [e["prefab_id"] for e in loaded["entities"]] == ["ghost"]
        entities = [{**e, "name": "Ghost", "layer": "entities"} for e in loaded["entities"]]


@pytest.mark.fast
def test_a_runtime_prefab_object_the_room_does_not_have_is_still_dropped() -> None:
    counts = saved_world.room_idless([RAW])
    bullet = {"prefab_id": "bullet", "name": "Bullet", "x": 1.0, "y": 1.0, "layer": "entities"}
    snap = _snapshot([LOADED, bullet], counts, {"night": True})
    assert [e["prefab_id"] for e in snap["entities"]] == ["ghost"]
