"""RV-1: a carried unresolved record is retried only in the room it belongs to (#462 review).

Room A's ``chest`` was missing at a load, so its record was kept unresolved (scene_path = room A). Later the player
saves in room B, a content update adds a ``chest`` to room B, and room B loads: the room-A record used to bind to room
B's chest (it jumped to A's place and took A's state) and left ``unresolved``, so the next save lost it for good.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from engine.save_runtime.entity_state import apply_entities_ex, unresolved_entry
from tests._b01_arena import Arena, close_window, goblin, hero, hp_of, make_window
from tests.test_b01_save_identity import Stub, id_record, stage


def _carried(room: str) -> list[dict[str, Any]]:
    return [unresolved_entry(id_record("chest", "Chest", 500, 600, 3), "entity_missing", room, "t0")]


@pytest.mark.fast
def test_a_record_carried_from_room_a_never_binds_to_room_bs_same_id_entity() -> None:
    carried = _carried("rooms/a.json")
    door, chest = Stub("Door", 10, 10, mesh_id="door"), Stub("Chest", 100, 100, 20, "chest")
    result = apply_entities_ex(stage(door, chest), [id_record("door", "Door", 10, 10, 20)],
                               scene_path="rooms/b.json", carried=carried, log=False)
    assert (chest.center_x, chest.center_y, chest.hp) == (100, 100, 20)
    assert (result.retried, result.unresolved) == (0, carried)


@pytest.mark.fast
def test_a_record_carried_from_room_a_binds_when_room_a_itself_loads() -> None:
    chest = Stub("Chest", 100, 100, 20, "chest")
    result = apply_entities_ex(stage(chest), [], scene_path="rooms/a.json", carried=_carried("rooms/a.json"),
                               log=False)
    assert (result.retried, result.unresolved) == (1, []) and (chest.center_x, chest.hp) == (500, 3)


@pytest.mark.fast
def test_the_same_room_spelled_differently_still_counts_as_its_room() -> None:
    chest = Stub("Chest", 100, 100, 20, "chest")
    result = apply_entities_ex(stage(chest), [], scene_path="rooms\\a.json", carried=_carried("rooms/a.json"),
                               log=False)
    assert result.retried == 1 and chest.hp == 3


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


@pytest.mark.integration
@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_a_save_in_room_b_keeps_room_as_record_and_room_bs_new_same_id_entity_is_untouched(arena: Arena) -> None:
    room_a = arena.room
    room_b = arena.root / "room_b.json"
    # room A has a chest; the player hurts it and saves
    arena.write_room(hero(), goblin("chest", 100, 100))
    arena.enter()
    arena.place(arena.by_id("chest"), 500, 600, hp=3)
    arena.save("s_a")
    # a content update removes room A's chest; Continue keeps its record unresolved
    arena.write_room(hero())
    arena.enter()
    assert arena.load("s_a")
    held = arena.held()
    assert [e["record"]["mesh_id"] for e in held] == ["chest"]
    # the player walks to room B (no chest yet) and saves there
    arena.room = room_b
    arena.write_room(hero())
    arena.enter()
    arena.save("s_b")
    assert [e["record"]["mesh_id"] for e in arena.unresolved("s_b")] == ["chest"]
    # a content update adds a chest to room B; Continue in room B
    arena.write_room(hero(), goblin("chest", 100, 100))
    assert arena.load("s_b")
    chest = arena.by_id("chest")
    assert (chest.center_x, chest.center_y, hp_of(chest)) == (100, 100, 20)
    # and the next save still carries room A's record
    arena.save("s_b2")
    assert [e["record"]["mesh_id"] for e in arena.unresolved("s_b2")] == ["chest"]
    assert room_a != room_b
