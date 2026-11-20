"""B-09: an object spawned during play that is gone by the next save stays gone.

After a load the composed save is the scene's authored list, so the snapshot (``build_scene_snapshot``) kept the saved
id-less objects (a projectile) with no live sprite, as it keeps a room's own object whose sprite is absent: an expired
projectile was written again and came back on every load, and each cycle's spawns piled up. The loader now hands the
controller what the room file has (``saved_world.room_idless``), and the snapshot drops the id-less objects only the
save carries (``saved_world.carried``) once their sprite is gone. Room-file objects are untouched.

Production snapshot and composer; sprites are the stand-ins the B-01b tests use. Fresh processes: the GPU-lane twin."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine.scene_loader import SceneLoader
from engine.scene_runtime import saved_world
from engine.scene_runtime.persistence import build_scene_snapshot

ROOM = "scenes/room.json"


def _ent(**kw: Any) -> dict[str, Any]:
    return {"x": 0.0, "y": 0.0, "layer": "entities", **kw}


def _sprite(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(mesh_entity_data=copy.deepcopy(data), center_x=data["x"], center_y=data["y"], scale=1.0,
                           angle=0.0, mesh_behaviour_configs=[])


def _snapshot(scene: dict[str, Any], sprites: list[SimpleNamespace], room_idless: Any, flags: Any = None) -> dict[str, Any]:
    window = SimpleNamespace(
        camera_controller=SimpleNamespace(zoom_state=SimpleNamespace(current=1.0, target=1.0, speed=5.0, min_zoom=0.5,
                                                                     max_zoom=2.0)),
        game_state=SimpleNamespace(snapshot=lambda: {}), scene_loader=SceneLoader(), get_flag=flags)
    controller = SimpleNamespace(window=window, _loaded_scene_source_data=copy.deepcopy(scene), all_sprites=sprites,
                                 layers={"entities": sprites}, tilemap_instance=None, _room_idless=room_idless)
    return build_scene_snapshot(cast(Any, controller))


def _names(snap: dict[str, Any]) -> list[Any]:
    return [e.get("id") or e.get("name") for e in snap["entities"]]


def _load(save: dict[str, Any], room: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """What a load of ``save`` over ``room`` hands the controller: the composed scene and the room's id-less counts."""
    return saved_world.compose(save, room, ROOM), saved_world.room_idless(room["entities"])


@pytest.mark.fast
def test_a_carried_runtime_object_without_a_sprite_is_not_written_again() -> None:
    scene = {"entities": [_ent(id="a"), _ent(name="proj")]}
    snap = _snapshot(scene, [_sprite(scene["entities"][0])], room_idless={})
    assert _names(snap) == ["a"]


@pytest.mark.fast
def test_a_carried_runtime_object_with_a_sprite_is_kept() -> None:
    scene = {"entities": [_ent(id="a"), _ent(name="proj", x=5.0)]}
    snap = _snapshot(scene, [_sprite(scene["entities"][0]), _sprite(scene["entities"][1])], room_idless={})
    assert _names(snap) == ["a", "proj"]


@pytest.mark.fast
def test_a_room_file_object_without_a_sprite_is_kept_as_today() -> None:
    scene = {"entities": [_ent(id="a"), _ent(id="b"), _ent(name="sign")]}
    snap = _snapshot(scene, [_sprite(scene["entities"][0])], room_idless={("sign", None): 1})
    assert _names(snap) == ["a", "b", "sign"]


@pytest.mark.fast
def test_not_loaded_from_a_save_nothing_is_dropped() -> None:
    scene = {"entities": [_ent(id="a"), _ent(name="proj")]}
    assert _names(_snapshot(scene, [_sprite(scene["entities"][0])], room_idless=None)) == ["a", "proj"]


@pytest.mark.fast
def test_a_flag_gated_carried_object_stays_while_its_gate_hides_it() -> None:
    gated = _ent(name="ghost", require_flags=["met"])
    scene = {"entities": [_ent(id="a"), gated]}
    sprites = [_sprite(scene["entities"][0])]
    assert _names(_snapshot(scene, sprites, {}, flags=lambda _f, _d=False: False)) == ["a", "ghost"]
    assert _names(_snapshot(scene, sprites, {}, flags=lambda _f, _d=False: True)) == ["a"]


@pytest.mark.fast
def test_a_room_object_removed_in_play_stays_removed_through_room_memory() -> None:
    room = {"entities": [_ent(id="a"), _ent(id="b")]}
    save = {"entities": [_ent(id="a")], "meta": {saved_world.ROOM_IDS: ["a", "b"]},
            "state": {"variables": {"room_memory": {saved_world.room_key(ROOM): {"removed": ["b"]}}}}}
    scene = saved_world.compose(save, room, ROOM)
    assert [e["id"] for e in scene["entities"]] == ["a"]


@pytest.mark.fast
def test_a_runtime_spawned_each_cycle_with_the_same_name_stays_flat() -> None:
    """spawn, save, load, expire, save, load ... through the production compose and snapshot."""
    room = {"entities": [_ent(id="hero", name="Hero"), _ent(name="sign", x=3.0)]}
    save: dict[str, Any] | None = None
    sizes = []
    for _cycle in range(5):
        scene, counts = (copy.deepcopy(room), saved_world.room_idless(room["entities"])) if save is None else _load(save, room)
        live = [_sprite(e) for e in scene["entities"] if not str(e.get("name", "")).startswith("proj")]  # expired
        live.append(_sprite(_ent(name="proj", x=50.0)))  # this cycle's spawn, the same name as last cycle's
        snap = _snapshot(scene, live, counts)
        snap["meta"] = {saved_world.ROOM_IDS: ["hero"]}
        save = snap
        sizes.append(len(snap["entities"]))
    assert sizes == [3] * 5
    assert sorted(e["name"] for e in save["entities"]) == ["Hero", "proj", "sign"]


@pytest.mark.fast
def test_carried_is_only_what_the_room_has_no_name_for_and_leaves_ided_objects_alone() -> None:
    entities = [_ent(id="a"), _ent(name="wolf"), _ent(name="wolf"), _ent(name="owl")]
    assert saved_world.carried(entities, {("wolf", None): 1}) == {3}  # (only "owl": the room has no owl)


# ---- owner challenge: a room-file id-less object and a runtime one with the SAME name and prefab, in either order ----
def _wolf(x: float) -> dict[str, Any]:
    return _ent(name="wolf", x=x)


@pytest.mark.fast
@pytest.mark.parametrize("runtime_first", [False, True])
def test_a_sprite_less_runtime_twin_never_costs_the_room_file_object_whichever_comes_first(runtime_first: bool) -> None:
    room_wolf, runtime_wolf = _wolf(1.0), _wolf(777.0)
    saved = [runtime_wolf, room_wolf] if runtime_first else [room_wolf, runtime_wolf]
    scene = {"entities": [_ent(id="a"), *saved]}
    counts = saved_world.room_idless([room_wolf])
    # (1) the room's wolf is live (moved), the runtime one expired
    live = _sprite({**room_wolf, "x": 5.0})
    snap = _snapshot(scene, [_sprite(scene["entities"][0]), live], counts)
    assert 5.0 in [e["x"] for e in snap["entities"] if e.get("name") == "wolf"]
    # (2) neither has a sprite: the room's must stay (the runtime twin may stay too: they can't be told apart)
    snap = _snapshot(scene, [_sprite(scene["entities"][0])], counts)
    assert 1.0 in [e["x"] for e in snap["entities"] if e.get("name") == "wolf"]


@pytest.mark.fast
def test_the_ambiguous_same_name_case_is_warned_not_dropped(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    logging.getLogger(saved_world.__name__).addHandler(caplog.handler)
    with caplog.at_level("WARNING", logger=saved_world.__name__):
        assert saved_world.carried([_wolf(1.0), _wolf(2.0)], {("wolf", None): 1}) == set()
    assert "can't be told apart" in caplog.text
