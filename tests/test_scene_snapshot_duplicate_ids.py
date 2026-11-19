"""B-01b: a scene snapshot (engine.scene_runtime.persistence.build_scene_snapshot) keeps every live entity that shares an
authored id or name, each with its own position and data. Before the fix every sprite sharing a key resolved to the same
authored entry, so the snapshot merged them (a console ``clone``, which copies the id, saved as one entity and lost the
clone's state). This is the snapshot layer only: ``saved_entities`` (behaviour state) is still name-keyed (B-01).

Real production code: the snapshot, the loader's scene defaults and the saved-world composer a load uses; sprites are
plain stand-ins carrying what the snapshot reads."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine.scene_loader import SceneLoader
from engine.scene_runtime import saved_world
from engine.scene_runtime.persistence import build_scene_snapshot

GOLDEN = Path(__file__).parent / "fixtures" / "b01b_snapshot_golden.json"


def _sprite(data: dict[str, Any], x: float | None = None, y: float | None = None, **extra: Any) -> SimpleNamespace:
    return SimpleNamespace(mesh_entity_data=copy.deepcopy(data), center_x=data.get("x", 0.0) if x is None else x,
                           center_y=data.get("y", 0.0) if y is None else y, scale=1.0, angle=0.0,
                           mesh_behaviour_configs=extra.get("behaviours", []))


def _snapshot(scene: dict[str, Any], sprites: list[SimpleNamespace]) -> dict[str, Any]:
    window = SimpleNamespace(
        camera_controller=SimpleNamespace(zoom_state=SimpleNamespace(current=1.0, target=1.0, speed=5.0, min_zoom=0.5,
                                                                     max_zoom=2.0)),
        game_state=SimpleNamespace(snapshot=lambda: {}), scene_loader=SceneLoader())
    controller = SimpleNamespace(window=window, _loaded_scene_source_data=copy.deepcopy(scene), all_sprites=sprites,
                                 layers={"entities": sprites}, tilemap_instance=None)
    return build_scene_snapshot(cast(Any, controller))


def _ent(**kw: Any) -> dict[str, Any]:
    return {"x": 0.0, "y": 0.0, "layer": "entities", **kw}


def _xy(snap: dict[str, Any]) -> list[tuple[Any, float, float, Any]]:
    return [(e.get("id") or e.get("name"), e["x"], e["y"], e.get("x_hp")) for e in snap["entities"]]


# ---- scenes WITHOUT duplicate keys: output must equal the base implementation's (recorded golden) ----
def _golden_cases() -> dict[str, tuple[dict[str, Any], list[SimpleNamespace]]]:
    a, b, c = _ent(id="a", x=10.0, y=20.0, x_hp=5), _ent(id="b", x=30.0, y=40.0), _ent(name="npc", x=1.0, y=2.0)
    prefab = _ent(id="p1", prefab_id="player", x=5.0, y=6.0, x_note="kept")
    beh = _ent(id="g", x=9.0, y=9.0)
    return {
        "unique_moved": ({"entities": [a, b]}, [_sprite(a, 11.5, 22.5), _sprite(b)]),
        "name_only_and_prefab": ({"entities": [c, prefab]}, [_sprite(c, 3.0, 4.0), _sprite(prefab, 7.0, 8.0)]),
        "authored_without_sprite": ({"entities": [a, b]}, [_sprite(a, 1.0, 1.0)]),
        "runtime_spawned": ({"entities": [a]}, [_sprite(a), _sprite(_ent(id="spawn1", x=50.0, y=60.0, x_hp=3)),
                                                _sprite(_ent(id="spawn2", x=51.0, y=61.0))]),
        "behaviours": ({"entities": [beh]}, [_sprite(beh, behaviours=[{"type": "patrol", "params": {"speed": 2}}])]),
        "empty": ({"entities": []}, []),
    }


@pytest.mark.fast
@pytest.mark.parametrize("case", sorted(_golden_cases()))
def test_scenes_without_duplicate_keys_snapshot_exactly_as_before(case: str) -> None:
    scene, sprites = _golden_cases()[case]
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(_snapshot(scene, sprites))) == golden[case]


# ---- duplicates ----
@pytest.mark.fast
def test_two_sprites_sharing_an_id_are_both_kept_with_their_own_transform_and_data() -> None:
    one, two = _ent(id="orc", x=10.0, y=10.0, x_hp=30), _ent(id="orc", x=200.0, y=300.0, x_hp=11)
    snap = _snapshot({"entities": [one, two]}, [_sprite(one, 15.0, 16.0), _sprite(two, 210.0, 310.0)])
    assert _xy(snap) == [("orc", 15.0, 16.0, 30), ("orc", 210.0, 310.0, 11)]


@pytest.mark.fast
def test_a_console_style_clone_sharing_the_id_is_its_own_record() -> None:
    orig = _ent(id="orc", name="orc", x=10.0, y=10.0, x_hp=30)
    clone = {**orig, "name": "orc_clone", "x": 99.0, "y": 98.0, "x_hp": 11}
    # the clone is listed FIRST: the original must still keep its own authored entry
    snap = _snapshot({"entities": [orig]}, [_sprite(clone), _sprite(orig, 12.0, 12.0)])
    by_name = {e["name"]: e for e in snap["entities"]}
    assert len(snap["entities"]) == 2
    assert (by_name["orc"]["x"], by_name["orc"]["x_hp"]) == (12.0, 30)
    assert (by_name["orc_clone"]["x"], by_name["orc_clone"]["y"], by_name["orc_clone"]["x_hp"]) == (99.0, 98.0, 11)


@pytest.mark.fast
def test_sprites_sharing_a_name_are_both_kept() -> None:
    one, two = _ent(name="guard", x=1.0, y=1.0, x_hp=1), _ent(name="guard", x=2.0, y=2.0, x_hp=2)
    snap = _snapshot({"entities": [one, two]}, [_sprite(one, 5.0, 5.0), _sprite(two, 6.0, 6.0)])
    assert _xy(snap) == [("guard", 5.0, 5.0, 1), ("guard", 6.0, 6.0, 2)]


@pytest.mark.fast
def test_three_duplicates_mixed_with_unique_and_runtime_entities() -> None:
    d = [_ent(id="d", x=float(i), y=float(i) * 2, x_hp=i) for i in (1, 2, 3)]
    u = _ent(id="u", x=7.0, y=7.0)
    sprites = [_sprite(d[2], 30.0, 31.0), _sprite(u, 8.0, 8.0), _sprite(d[0], 10.0, 11.0), _sprite(d[1], 20.0, 21.0),
               _sprite(_ent(id="rt", x=70.0, y=71.0, x_hp=9))]
    snap = _snapshot({"entities": [d[0], d[1], d[2], u]}, sprites)
    got = {(e["id"], e["x_hp"] if "x_hp" in e else None): (e["x"], e["y"]) for e in snap["entities"]}
    assert len(snap["entities"]) == 5
    assert got == {("d", 1): (10.0, 11.0), ("d", 2): (20.0, 21.0), ("d", 3): (30.0, 31.0), ("u", None): (8.0, 8.0),
                   ("rt", 9): (70.0, 71.0)}


@pytest.mark.fast
def test_more_sprites_than_authored_entries_each_extra_is_appended_not_merged() -> None:
    one = _ent(id="orc", x=1.0, y=1.0, x_hp=1)
    extra = [_ent(id="orc", x=float(i), y=float(i), x_hp=i) for i in (2, 3)]
    snap = _snapshot({"entities": [one]}, [_sprite(one), *[_sprite(e) for e in extra]])
    assert sorted(_xy(snap), key=lambda t: t[3]) == [("orc", 1.0, 1.0, 1), ("orc", 2.0, 2.0, 2), ("orc", 3.0, 3.0, 3)]


@pytest.mark.fast
def test_sprites_whose_data_was_edited_since_loading_pair_with_entries_in_authored_order() -> None:
    one, two = _ent(id="orc", x=10.0, y=10.0, x_hp=30), _ent(id="orc", x=200.0, y=300.0, x_hp=11)
    edited = [{**one, "x": 11.0}, {**two, "x": 201.0}]  # no sprite's data equals an authored entry any more
    snap = _snapshot({"entities": [one, two]}, [_sprite(edited[0], 15.0, 16.0), _sprite(edited[1], 210.0, 310.0)])
    assert _xy(snap) == [("orc", 15.0, 16.0, 30), ("orc", 210.0, 310.0, 11)]


@pytest.mark.fast
def test_the_ambiguous_case_keeps_both_records_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    one = _ent(id="orc", x=1.0, y=1.0, x_hp=1)
    clone = _ent(id="orc", x=50.0, y=50.0, x_hp=2)
    with caplog.at_level("WARNING", logger="engine.scene_runtime.persistence"):
        snap = _snapshot({"entities": [one]}, [_sprite(one), _sprite(clone)])
    assert len(snap["entities"]) == 2
    assert any("orc" in r.getMessage() for r in caplog.records)


# ---- round trip: the saved room the load composes still holds both ----
@pytest.mark.fast
def test_both_duplicates_come_back_through_the_saved_world_composer() -> None:
    one, two = _ent(id="orc", x=10.0, y=10.0, x_hp=30), _ent(id="orc", x=200.0, y=300.0, x_hp=11)
    room = {"entities": [one, two]}
    snap = _snapshot(room, [_sprite(one, 15.0, 16.0), _sprite(two, 210.0, 310.0)])
    save = {"entities": json.loads(json.dumps(snap["entities"])), "meta": {saved_world.ROOM_IDS: ["orc"]}}
    out = saved_world.compose(save, room, "scenes/room.json")
    assert [(e["x"], e["y"]) for e in out["entities"]] == [(15.0, 16.0), (210.0, 310.0)]
