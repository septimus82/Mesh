"""B-01b: ``saved_world.compose`` (the scene a load builds from a save and its room as it is now) pairs the k-th saved
entity carrying an id with the k-th authored entry carrying that id, instead of taking every saved entity's authored
fields from the last entry with the id. Ids unique on both sides compose exactly as before (recorded golden)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from engine.scene_runtime import saved_world

GOLDEN = Path(__file__).parent / "fixtures" / "b01b_compose_golden.json"
ROOM = "scenes/room.json"


def _e(i: str, x: float, tags: list[str] | None = None, **kw: Any) -> dict[str, Any]:
    return {"id": i, "x": x, "y": 0.0, **({"tags": tags} if tags else {}), **kw}


def _save(entities: list[dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    return {"entities": entities, "meta": {saved_world.ROOM_IDS: ids}, "state": {"variables": {}}}


def _golden_cases() -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    room = {"entities": [_e("a", 1, ["ta"]), _e("b", 2, ["tb"]), _e("c", 3, ["tc"])], "settings": {}}
    return {
        "unique_moved": (_save([_e("a", 11), _e("b", 22), _e("c", 33)], ["a", "b", "c"]), room),
        "room_added_object": (_save([_e("a", 11), _e("b", 22)], ["a", "b"]), room),
        "room_deleted_object": (_save([_e("a", 11), _e("b", 22), _e("c", 33), _e("d", 44)], ["a", "b", "c", "d"]), room),
        "player_spawned_extra": (_save([_e("a", 11), _e("zz", 5, ["spawn"])], ["a"]), room),
        "removed_in_play": (
            {**_save([_e("a", 11)], ["a", "b"]),
             "state": {"variables": {"room_memory": {saved_world.room_key(ROOM): {"removed": ["b"]}}}}}, room),
    }



def _captured(caplog: pytest.LogCaptureFixture, name: str) -> Any:
    """The engine's loggers do not propagate to the root: attach caplog's handler to this one."""
    logging.getLogger(name).addHandler(caplog.handler)
    return caplog.at_level("WARNING", logger=name)


@pytest.mark.fast
@pytest.mark.parametrize("case", sorted(_golden_cases()))
def test_ids_unique_on_both_sides_compose_exactly_as_before(case: str) -> None:
    save, room = _golden_cases()[case]
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(saved_world.compose(save, room, ROOM))) == golden[case]


def _twins_room() -> dict[str, Any]:
    return {"entities": [_e("orc", 10, ["hp30"]), _e("orc", 200, ["hp11"])], "settings": {}}


def _got(out: dict[str, Any]) -> list[tuple[float, Any]]:
    return [(e["x"], e.get("tags")) for e in out["entities"]]


@pytest.mark.fast
def test_twins_pair_with_their_own_authored_entry_by_order() -> None:
    save = _save([_e("orc", 15, ["hp30"]), _e("orc", 210, ["hp11"])], ["orc"])
    assert _got(saved_world.compose(save, _twins_room(), ROOM)) == [(15, ["hp30"]), (210, ["hp11"])]


@pytest.mark.fast
def test_more_saved_than_authored_the_extra_keeps_its_saved_fields_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    room = {"entities": [_e("orc", 10, ["hp30"])], "settings": {}}
    save = _save([_e("orc", 15, ["hp30"]), _e("orc", 210, ["saved-extra"])], ["orc"])
    with _captured(caplog, "engine.scene_runtime.saved_world"):
        out = saved_world.compose(save, room, ROOM)
    assert _got(out) == [(15, ["hp30"]), (210, ["saved-extra"])]
    assert any("orc" in r.getMessage() for r in caplog.records)


@pytest.mark.fast
def test_fewer_saved_than_authored_the_rest_follow_the_existing_added_logic(caplog: pytest.LogCaptureFixture) -> None:
    save = _save([_e("orc", 15, ["hp30"])], ["orc"])
    with _captured(caplog, "engine.scene_runtime.saved_world"):
        out = saved_world.compose(save, _twins_room(), ROOM)
    assert _got(out) == [(15, ["hp30"])]  # (the id is already `have`: an unsaved duplicate is not re-added, as today)
    assert any("orc" in r.getMessage() for r in caplog.records)


@pytest.mark.fast
def test_a_duplicate_removed_from_the_room_since_the_save_keeps_its_saved_twin_as_saved() -> None:
    room = {"entities": [_e("orc", 10, ["hp30"])], "settings": {}}  # one twin deleted from the room file
    save = _save([_e("orc", 15, ["hp30"]), _e("orc", 210, ["hp11"])], ["orc"])
    assert _got(saved_world.compose(save, room, ROOM)) == [(15, ["hp30"]), (210, ["hp11"])]
