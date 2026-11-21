"""Undo steps share one copy of every room they did not change (Astra, 12 November).

Each undo step used to hold its own copy of every room that was open, changed or not: after one look into a large
room, every later edit anywhere kept another copy of it, a hundred of them at the history's limit. Now the history
keeps one private copy of each version of a room (``Project._freeze``) and the steps that did not change the room hold
that same copy.

What must not change, and is checked here against a record kept beside the project (``Recorded``): every undo and
redo gives back exactly the documents that were there, to the type of each number and the order of each key; one
step an edit or a batch; a failed batch leaves nothing; and nothing done to the documents afterwards, even in place,
reaches a step already taken.

A real project on disk, no window. The memory test compares two sessions with each other (never with a number of
bytes); ``tooling/undo_history_memory.py`` measures the amounts.
"""

from __future__ import annotations

import gc
import json
import random
import shutil
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from engine import authoring
from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_project import UNDO_LIMIT, Project

pytestmark = pytest.mark.integration  # (a real project on disk)

BIG_OBJECTS = 1500


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """``start``, ``small`` (five crates), ``other`` (two) and ``big`` (1,500 objects), saved."""
    root = tmp_path_factory.mktemp("undo_sharing") / "game"
    create_project(root, "Game", template_id="blank")
    project = _open(root)
    for label in ("Small", "Other", "Big"):
        project.add_room(label)
    for key, count in (("small", 5), ("other", 2), ("big", 1)):
        for n in range(count):
            project.edit_scene(lambda room, key=key, n=n: ops.place_blank(room, key, f"Crate {n}", 32 + 32 * n, 64)[0], key)
    project.save()
    path = root / project.path("big")
    room = json.loads(path.read_text(encoding="utf-8"))
    crate = room["entities"][-1]
    room["entities"] = [{**crate, "id": f"big_thing_{n}", "name": f"Thing {n}", "x": 32 + 16 * (n % 50), "y": 32 + 16 * (n // 50),
                         "tags": ["a", "b"], "notes": {"n": n, "on": True, "weight": 1.5}} for n in range(BIG_OBJECTS)]
    path.write_text(json.dumps(room, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return root


@pytest.fixture()
def root(made: Path, tmp_path: Path) -> Path:
    return Path(shutil.copytree(made, tmp_path / "game", copy_function=shutil.copy2))


def _open(root: Path) -> Project:
    return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def exact(project: Project) -> dict[str, Any]:
    """Every document as text: a 1 that became 1.0 or True, or two keys that changed places, is a difference. A room
    of the world not read yet is None."""
    return {"world": json.dumps(project.world), "player": json.dumps(project.player), "current": project.current,
            "rooms": {key: json.dumps(project.scenes[key]) if key in project.scenes else None
                      for key in project.world.get("scenes") or {}}}


def same(project: Project, then: dict[str, Any]) -> bool:
    """The project's documents are exactly what ``then`` (an earlier ``exact``) recorded. A room not read yet then
    is, now that it has been read, the room as first read: nothing had changed it."""
    now = exact(project)
    if (now["world"], now["player"], now["current"], set(now["rooms"])) != (
            then["world"], then["player"], then["current"], set(then["rooms"])):
        return False
    for key, text in now["rooms"].items():
        was = then["rooms"][key]
        if was is None and text is not None:
            was = json.dumps(project._as_read[key])
        if text != was:
            return False
    return True


def state_text(state: Any) -> str:
    return json.dumps({"world": state.world, "rooms": state.scenes, "player": state.player, "current": state.current,
                       "dirty": sorted(state.dirty)})


def move(project: Project, key: str, n: int, entity: int = 0) -> None:
    target = project.scene(key)["entities"][entity]["id"]
    project.edit_scene(lambda room: ops.move_entity(room, target, 100.0 + n, 64.0), key)


def look(project: Project, key: str) -> None:
    """The person opens a room and comes back."""
    here = project.current
    project.current = key
    project.scene()
    project.current = here


# --- sharing ---------------------------------------------------------------------------------------------


def test_steps_hold_one_copy_of_a_room_they_did_not_change(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    for n in range(30):
        move(project, "small", n)
    big = {id(state.scenes["big"]) for state in project._undo}
    small = {id(state.scenes["small"]) for state in project._undo}
    # (This is what failed before: 30 copies of the big room, one a step.)
    assert len(big) == 1 and len(small) == 30, "one copy of the room nobody changed; one of the edited room per step"
    kept = project._undo[0].scenes["big"]
    assert kept is project._as_read["big"], "and that copy is the room as first read: no copy of its own at all"
    assert kept is not project.scenes["big"] and kept == project.scenes["big"], "never the room being edited itself"


def test_a_room_changed_in_a_step_gets_its_copy_and_later_steps_share_the_new_one(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    move(project, "small", 1)
    move(project, "big", 2)   # the big room changes once
    move(project, "small", 3)
    move(project, "small", 4)
    copies = [id(state.scenes["big"]) for state in project._undo]
    assert copies[0] == copies[1] != copies[2] == copies[3], "before the change one copy, after it another"
    assert project._undo[1].scenes["big"]["entities"][0]["x"] != project._undo[2].scenes["big"]["entities"][0]["x"]


def test_history_does_not_grow_with_a_large_room_that_was_only_looked_at(root: Path) -> None:
    """Two sessions of the same 40 edits to the small room, one after looking into the big room. Compared with each
    other: the big room's presence may not multiply what the history holds (it used to, by a copy a step)."""
    def session(visit: bool) -> tuple[int, int]:
        project = _open(root)
        look(project, "small")
        if visit:
            look(project, "big")
        gc.collect()
        tracemalloc.start()
        try:
            before = tracemalloc.get_traced_memory()[0]
            for n in range(40):
                move(project, "small", n)
            gc.collect()
            grown = tracemalloc.get_traced_memory()[0] - before
        finally:
            tracemalloc.stop()
        return grown, len(json.dumps(project.scenes))

    plain, small_documents = session(False)
    visited, all_documents = session(True)
    assert all_documents > 20 * small_documents, "the big room dwarfs the rest (or this compares nothing)"
    assert visited < 2 * plain, (f"40 edits to the small room held {visited} bytes after the big room was opened, "
                                 f"{plain} without it: the history grows with a room nobody changed")


def test_what_is_dropped_from_the_history_lets_its_copies_go(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    for n in range(5):
        move(project, "big", n)  # five versions of the big room
    for n in range(UNDO_LIMIT + 20):
        move(project, "small", n)  # ... all pushed out of the history
    assert len(project._undo) == UNDO_LIMIT
    assert len({id(state.scenes["big"]) for state in project._undo}) == 1
    for _ in range(40):
        assert project.undo()
    assert len(project._redo) == 40
    move(project, "small", 999)  # a new edit: nothing left to redo
    assert project._redo == [] and not project.can_redo() and len(project._undo) == UNDO_LIMIT - 40 + 1


# --- exactness and independence ------------------------------------------------------------------------------


class Recorded:
    """The documents after every step, kept as text beside the project: what undo and redo must give back. (Dirty
    flags across saves have tests of their own, tests/test_studio_room_undo_save.py: the documents are compared.)"""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.done = [exact(project)]
        self.undone: list[dict[str, Any]] = []

    def step(self) -> None:
        """An edit was made (one undo step)."""
        self.done.append(exact(self.project))
        del self.done[:-(UNDO_LIMIT + 1)]
        self.undone.clear()

    def undo(self) -> None:
        assert self.project.undo()
        self.undone.append(self.done.pop())
        self.check()

    def redo(self) -> None:
        assert self.project.redo()
        self.done.append(self.undone.pop())
        self.check()

    def check(self) -> None:
        assert same(self.project, self.done[-1])
        assert len(self.project._undo) == len(self.done) - 1 and len(self.project._redo) == len(self.undone)


def test_undo_and_redo_give_back_exactly_what_was_there_through_a_long_mixed_session(root: Path) -> None:
    """Edits in several rooms, rooms opened for the first time part way, batches, failed batches, a new room, saves,
    undo and redo in runs: after every one, the documents are what the record says, exactly."""
    rng = random.Random(20261112)
    project = _open(root)
    record = Recorded(project)
    rooms = ["start", "small"]
    seen = {"steps": 0, "big": 0, "undone": 0, "redone": 0, "saves": 0, "failed": 0, "batches": 0}

    def pick() -> str:  # (the large room is edited now and then: every edit of it copies it, which takes time)
        return "big" if "big" in rooms and rng.random() < 0.15 else rng.choice([r for r in rooms if r != "big"])

    for turn in range(220):
        roll = rng.random()
        if turn in (15, 60):  # a room read for the first time, after earlier edits (reading is not an edit)
            rooms.append("big" if turn == 15 else "other")
            look(project, rooms[-1])
        elif roll < 0.45:
            key = pick()
            if project.scene(key)["entities"]:
                move(project, key, turn, rng.randrange(len(project.scene(key)["entities"])))
                record.step()
                seen["steps"] += 1
                seen["big"] += key == "big"
        elif roll < 0.55:
            key = rng.choice([r for r in rooms if r != "big"])
            project.edit_scene(lambda room, key=key, turn=turn: ops.place_blank(room, key, f"New {turn}", 16 + turn, 96)[0], key)
            record.step()
        elif roll < 0.62:  # a batch across two rooms: one step
            a, b = rng.sample([r for r in rooms if r != "big"], 2)
            authoring.apply(project, [{"op": "place_blank", "room": a, "name": f"A{turn}", "x": 8, "y": 8},
                                      {"op": "place_blank", "room": b, "name": f"B{turn}", "x": 8, "y": 8}])
            record.step()
            seen["batches"] += 1
        elif roll < 0.68:  # a batch that fails part way: no step, nothing changed
            before = exact(project)
            with pytest.raises(authoring.ChangeError):
                authoring.apply(project, [{"op": "place_blank", "room": rooms[0], "name": "Lost", "x": 8, "y": 8},
                                          {"op": "move_entity", "room": rooms[0], "id": "nobody", "x": 1, "y": 1}])
            assert same(project, before)
            seen["failed"] += 1
        elif roll < 0.72 and turn > 100 and "cellar" not in project.keys_seen:
            project.add_room("Cellar")
            rooms.append("cellar")
            record.step()
        elif roll < 0.76:  # (which room is open is part of the present state, not a step)
            project.current = rng.choice([r for r in rooms if r in project.world["scenes"]])
            project.scene()
            record.done[-1] = exact(project)
        elif roll < 0.80 and project.is_dirty:
            project.save()
            seen["saves"] += 1
        elif roll < 0.92:
            for _ in range(rng.randint(1, 6)):
                if project.can_undo():
                    record.undo()
                    seen["undone"] += 1
            rooms = [r for r in rooms if r in project.world["scenes"]]
        else:
            for _ in range(rng.randint(1, 6)):
                if project.can_redo():
                    record.redo()
                    seen["redone"] += 1
            if "cellar" in project.world["scenes"] and "cellar" not in rooms:
                rooms.append("cellar")
        record.check()
    assert min(seen.values()) >= 3, seen  # (the session really did all of these)
    while project.can_undo():  # and all the way back, then all the way forward
        record.undo()
    while project.can_redo():
        record.redo()


@pytest.mark.parametrize("how", ["an int that became a float", "a flag that became a number", "keys that changed places"])
def test_a_change_that_equals_what_was_there_is_still_a_change(root: Path, how: str) -> None:
    """``==`` calls 1, 1.0 and True the same and ignores the order of keys; a saved file does not. A step holds the
    room exactly as it was."""
    project = _open(root)
    look(project, "big")
    look(project, "small")

    def change(room: dict) -> dict:
        out = json.loads(json.dumps(room))
        thing = out["entities"][7]
        if how == "an int that became a float":
            thing["x"] = float(thing["x"])
        elif how == "a flag that became a number":
            thing["notes"]["on"] = 1
        else:
            thing["notes"] = dict(reversed(list(thing["notes"].items())))
        return out

    before = exact(project)
    project.edit_scene(change, "big")
    after = exact(project)
    assert after["rooms"]["big"] != before["rooms"]["big"], "different as text"
    assert json.loads(after["rooms"]["big"]) == json.loads(before["rooms"]["big"]), "and equal by =="
    move(project, "small", 1)  # a later step, in another room: it must hold the big room as it is now, not as it was
    assert project.undo() and same(project, after)
    assert project.undo() and same(project, before)
    assert project.redo() and same(project, after)


def test_nothing_done_to_the_documents_afterwards_reaches_a_step_already_taken(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    for n in range(4):
        move(project, "small", n)
    held = [state_text(state) for state in project._undo]
    # In place, deep inside, in the room being edited, in the view editors are given and in the world:
    project.scenes["big"]["entities"][0]["notes"]["n"] = "scribbled"
    project.scenes["big"]["entities"].append({"id": "intruder"})
    project.scene("small")["entities"][0]["name"] = "renamed in the view"
    project.world["scenes"]["small"]["label"] = "relabelled in place"
    assert [state_text(state) for state in project._undo] == held, "a step already taken never changes"
    move(project, "small", 9)  # the next step sees the big room as it now is: a copy of its own
    assert project._undo[-1].scenes["big"] is not project._undo[0].scenes["big"]
    assert project._undo[-1].scenes["big"]["entities"][-1] == {"id": "intruder"}
    assert [state_text(state) for state in project._undo[:-1]] == held
    assert project.undo() and project.undo()  # back before the scribble's step: the big room as it was
    assert project.scenes["big"]["entities"][0]["notes"]["n"] == 0 and len(project.scenes["big"]["entities"]) == BIG_OBJECTS
    project.scenes["big"]["entities"][1]["name"] = "changed after being restored"  # the restored room is not the step's
    assert [state_text(state) for state in project._undo] == held[:len(project._undo)]
    assert all("changed after being restored" not in state_text(state) for state in project._redo)


def test_a_room_first_read_after_a_step_comes_back_on_undo_as_a_room_of_its_own(root: Path) -> None:
    """Undo to a step taken before a room was first read: the room comes back as first read (#462 S2), and it is a
    room to edit, not the copy the project keeps of it as first read: changing it in place leaves that copy alone."""
    project = _open(root)
    move(project, "small", 1)  # (two steps that know nothing of "other")
    move(project, "small", 2)
    look(project, "other")
    as_read = json.dumps(project._as_read["other"])
    move(project, "other", 3)
    assert project.undo() and project.undo()
    room = project.scenes["other"]
    assert json.dumps(room) == as_read
    assert room is not project._as_read["other"]
    room["entities"][0]["x"] = -1.0  # (in place, as no operation does: the kept copy must not see it)
    room["entities"].append({"id": "stray"})
    assert json.dumps(project._as_read["other"]) == as_read
    assert project.undo()  # (to the first step: the room as first read again, not what was done to it in place)
    assert json.dumps(project.scenes["other"]) == as_read


def test_undo_leaves_a_room_it_does_not_change_alone_and_replaces_one_it_does(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    move(project, "small", 1)
    move(project, "big", 2)
    big, small, view = project.scenes["big"], project.scenes["small"], project.scene("big")
    assert project.undo()  # undoes the big room's move: the small room is the same object, untouched
    assert project.scenes["small"] is small and project.scenes["big"] is not big
    assert project.scenes["big"]["entities"][0]["x"] != big["entities"][0]["x"]
    assert project.scene("big") is not view  # (and what editors are shown is the restored room)
    big = project.scenes["big"]
    assert project.undo()  # undoes the small room's move: now the big room stays
    assert project.scenes["big"] is big and project.scenes["small"] is not small
    assert project.redo() and project.redo() and project.scenes["big"]["entities"][0]["x"] == 102.0
    assert project.undo()  # the big room is restored to what the first step holds ...
    move(project, "small", 7)  # ... and a new step, taken from the restored room, holds that same copy again
    assert project._undo[-1].scenes["big"] is project._undo[0].scenes["big"] is project._as_read["big"]


def test_a_failed_batch_puts_everything_back_and_the_history_goes_on_sharing(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    look(project, "other")
    move(project, "small", 1)
    before, steps = exact(project), len(project._undo)
    with pytest.raises(authoring.ChangeError):
        authoring.apply(project, [{"op": "move_entity", "room": "big", "id": "big_thing_3", "x": 5, "y": 5},
                                  {"op": "place_blank", "room": "small", "name": "Half", "x": 8, "y": 8},
                                  {"op": "move_entity", "room": "other", "id": "nobody", "x": 1, "y": 1}])
    assert same(project, before) and len(project._undo) == steps and not project.can_redo()
    move(project, "small", 2)
    assert project._undo[-1].scenes["big"] is project._undo[0].scenes["big"], "the same copy as before the failed batch"


def test_an_accepted_batch_is_one_step_and_shares_what_it_did_not_touch(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    look(project, "other")
    move(project, "small", 1)
    revision = project.revision
    out = authoring.apply(project, [{"op": "place_blank", "room": "small", "name": "One", "x": 8, "y": 8},
                                    {"op": "place_blank", "room": "other", "name": "Two", "x": 8, "y": 8}])
    assert out["ok"] and len(project._undo) == 2 and project.revision == revision + 1
    assert project._undo[1].scenes["big"] is project._undo[0].scenes["big"]
    after = exact(project)
    assert project.undo() and "One" not in str(exact(project)) and "Two" not in str(exact(project))
    assert project.redo() and same(project, after)


def test_saved_undone_saved_redone_saved_and_reopened_with_a_large_room_open(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    moved = {key: project.scene(key)["entities"][0]["id"] for key in ("small", "big")}
    was = {key: project.scene(key)["entities"][0]["x"] for key in ("small", "big")}
    move(project, "small", 1)
    move(project, "big", 2)
    edited = exact(project)
    assert sorted(project.save()) == sorted([project.path("big"), project.path("small")])
    files_edited = {key: (root / project.path(key)).read_bytes() for key in ("big", "small")}
    assert project.undo() and project.undo()
    project.save()
    reopened = _open(root)  # (a saved room's objects may be in another order: found by id)
    assert {key: ops.find_entity(reopened.scene(key), moved[key])["x"] for key in moved} == was
    assert project.redo() and project.redo()
    project.save()
    assert {key: (root / project.path(key)).read_bytes() for key in ("big", "small")} == files_edited
    again = _open(root)
    look(again, "big")
    look(again, "small")
    for key in ("big", "small"):
        assert json.loads(exact(again)["rooms"][key]) == json.loads(edited["rooms"][key])


def test_a_room_that_will_not_pickle_gets_a_copy_of_its_own_as_it_always_did(root: Path) -> None:
    project = _open(root)
    look(project, "small")
    odd = project.scenes["small"]["odd"] = lambda: None  # (never in a real project: something a pickle refuses)
    project.edit_scene(lambda room: {**room, "name": "Renamed"}, "start")
    held = project._undo[-1].scenes["small"]
    assert held is not project.scenes["small"] and held["odd"] is odd  # (a deep copy keeps a function as it is)
    assert project.undo() and project.scenes["small"]["odd"] is odd and project.scenes["small"] is not held
    assert project.redo() and project.scenes["start"]["name"] == "Renamed"


def test_a_dry_run_s_copy_of_the_project_reads_rooms_and_edits_with_a_history_of_its_own(root: Path) -> None:
    project = _open(root)
    look(project, "big")
    move(project, "small", 1)
    trial = project.clone()
    move(trial, "other", 5)  # a room the copy reads for the first time
    assert exact(project)["rooms"]["other"] is None and exact(trial)["rooms"]["other"] is not None
    assert trial.can_undo() and len(trial._undo) == 1 and len(project._undo) == 1
    assert trial.undo() and len(project._undo) == 1 and not trial.can_undo()
