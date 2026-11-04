"""#462 S1-ID: an AI proposal about an object never lands on a different object that took its id since.

An object's id is made from its room, type and spot (``make_entity_id``), unique only among the objects there now
(``unique_entity_id``). Delete an object and place another of the same type on the same spot, and the newcomer gets
the deleted one's id. A proposal the AI made about the first object is kept pinned to that id (S1), so accepting it
would change the newcomer, a different object, without a conflict when the newcomer happens to differ only in what
the proposal doesn't write.

Each test runs a real StudioAIHost on its loopback bridge, the AI going through ``authoring_session`` (what the MCP
tools and ``mesh author`` call), and the person editing Studio's own documents.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import authoring, authoring_session
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (a loopback bridge and a real project on disk, as the F6 and S1 tests)
ROOM = "packs/core_regions/scenes/start.json"


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window: the project as Studio holds it."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM))

    def on_ai_proposal(self, proposal: Any) -> None:
        pass

    def on_ai_decided(self, proposal: Any) -> None:
        pass


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studio(root: Path) -> Iterator[tuple[_Studio, StudioAIHost, str]]:
    """Mesh Studio with the project open, a Warden at (0, 0) in its start room, its live session running."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    person = _Studio(Project(root, config["world_file"]))
    authoring.apply(person.project, [{"op": "place_prefab", "prefab": "person", "x": 0, "y": 0},
                                     {"op": "rename_entity", "entity_id": "@0", "name": "Warden"}])
    warden = next(e["id"] for e in person.project.scene()["entities"] if e.get("name") == "Warden")
    host = StudioAIHost(person)
    host.start()
    stop = threading.Event()

    def pump() -> None:
        while not stop.is_set():
            host.drain()
            time.sleep(0.01)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    yield person, host, warden
    stop.set()
    thread.join(timeout=2)
    host.stop()


def _entity(project: Project, entity_id: str) -> dict[str, Any]:
    return next(e for e in project.scene()["entities"] if e.get("id") == entity_id)


def _propose(root: Path, host: StudioAIHost, changes: list[dict[str, Any]], revision: int) -> Any:
    staged = authoring_session.propose(root, changes, base_revision=revision)
    assert staged["ok"], staged
    return next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"])


def _delete(project: Project, entity_id: str) -> None:
    project.edit_scene(lambda room: authoring.ops.remove_entity(room, entity_id))


def _place(project: Project, x: float, y: float, name: str | None = None) -> str:
    changes: list[dict[str, Any]] = [{"op": "place_prefab", "prefab": "person", "x": x, "y": y}]
    if name:
        changes.append({"op": "rename_entity", "entity_id": "@0", "name": name})
    return str(authoring.apply(project, changes)["created"][0])


# --------------------------------------------------------------------- the reported case

def test_a_proposal_about_a_deleted_object_never_lands_on_the_newcomer_that_took_its_id(root: Path,
                                                                                      studio: Any) -> None:
    """The AI proposes moving the Warden. The person deletes the Warden and places a new person, the Scout, on the
    same spot. Accepting must not move the Scout (a different object), nor report success."""
    person, host, warden = studio
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _delete(person.project, warden)
    scout = _place(person.project, 0, 0, "Scout")
    before = copy.deepcopy(person.project.all_documents())

    result = host.accept(proposal)

    scout_now = _entity(person.project, scout)
    assert (scout_now["x"], scout_now["y"]) == (0.0, 0.0), ("the Scout isn't moved", scout, warden)
    assert result["ok"] is False, result
    assert person.project.all_documents() == before, "nothing applied"


# --------------------------------------------------------------------- the identity contract

def _ids(project: Project) -> list[str]:
    return [str(e["id"]) for e in project.scene()["entities"]]


def test_every_new_object_gets_an_id_no_object_has_had_this_session(root: Path, studio: Any) -> None:
    """Placed twice on one spot, both deleted, placed again: three different ids, never one given back."""
    person, _host, warden = studio
    first, second = _place(person.project, 300, 300), _place(person.project, 300, 300)
    _delete(person.project, first)
    _delete(person.project, second)
    third = _place(person.project, 300, 300)
    assert len({first, second, third}) == 3 and third.startswith(first), (first, second, third)
    _delete(person.project, warden)
    assert _place(person.project, 0, 0) != warden, "the deleted Warden's id isn't given to the newcomer"


def test_studio_placement_and_paste_never_reuse_an_id_either(root: Path, studio: Any) -> None:
    """Mesh Studio places and pastes through Project.edit_scene (not authoring.apply): the same promise."""
    person, _host, warden = studio
    original = copy.deepcopy(_entity(person.project, warden))
    _delete(person.project, warden)
    prefab = next(p for p in authoring.prefabs(person.project) if p["id"] == "person")
    made: list[str] = []

    def place(room: dict[str, Any]) -> dict[str, Any]:
        new_room, new_id = authoring.ops.place_prefab(room, person.project.current, prefab, 0, 0)
        made.append(new_id)
        return new_room

    person.project.edit_scene(place)
    assert made[0] != warden
    pasted: list[str] = []

    def paste(room: dict[str, Any]) -> dict[str, Any]:
        new_room, new_id = authoring.ops.paste_entity(room, person.project.current, original, 0, 0)
        pasted.append(new_id)
        return new_room

    _delete(person.project, made[0])
    person.project.edit_scene(paste)
    assert pasted[0] not in (warden, made[0])
    # placed in Studio, undone, placed again on the same spot: a new id (undo doesn't give it back to another)
    person.project.edit_scene(place)
    assert person.project.undo() and made[-1] not in _ids(person.project)
    person.project.edit_scene(place)
    assert made[-1] != made[-2], made


def test_undoing_a_deletion_brings_back_the_same_object_and_its_proposal_still_applies(root: Path,
                                                                                   studio: Any) -> None:
    """The contract: undo restores the very object (same id, same incarnation), so a proposal about it applies;
    an object undone out of existence still keeps its id from being given to the next one."""
    person, host, warden = studio
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _delete(person.project, warden)
    assert person.project.undo() and warden in _ids(person.project)
    assert host.accept(proposal)["ok"] is True and _entity(person.project, warden)["y"] == 100.0

    scout = _place(person.project, 500, 500)
    assert person.project.undo() and scout not in _ids(person.project)
    assert _place(person.project, 500, 500) != scout, "an object undone away keeps its id from the next one"


def test_an_ai_proposal_placing_on_a_deleted_objects_spot_gets_a_new_id_and_its_names_resolve(root: Path,
                                                                                           studio: Any) -> None:
    """Authoring/MCP: the AI places a person where the Warden was, names it, then moves it by that name. Its preview
    (a dry run on a copy) gives it the id the real edit will, so the name still finds it when accepted."""
    person, host, warden = studio
    _delete(person.project, warden)
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "place_prefab", "prefab": "person", "x": 0, "y": 0},
                                     {"op": "rename_entity", "entity_id": "@0", "name": "Ranger"},
                                     {"op": "move_entity", "entity_id": "Ranger", "x": 0, "y": 32}],
                        read["revision"])

    result = host.accept(proposal)

    assert result["ok"] is True, result
    ranger = str(proposal.created[0])
    assert ranger != warden and _entity(person.project, ranger)["y"] == 32.0


def test_ids_already_in_a_project_never_change_and_save_and_reopen_keep_the_new_ones(root: Path,
                                                                                    studio: Any) -> None:
    person, _host, warden = studio
    person.project.save()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    reopened = Project(root, config["world_file"])
    assert _ids(reopened) == _ids(person.project), "opening a saved project changes no id"
    authoring.apply(reopened, [{"op": "remove_entity", "entity_id": warden}])  # (in a batch: authoring, an AI)
    newcomer = _place(reopened, 0, 0)  # (an object read from disk this session: its id is kept from the next one too)
    assert newcomer != warden
    reopened.save()
    again = Project(root, config["world_file"])
    assert newcomer in _ids(again) and warden not in _ids(again)


def test_an_older_room_without_ids_still_gets_the_same_ids_as_before(root: Path) -> None:
    """Legacy scenes: an object saved without an id gets the one it always got (room, name, spot) when the room is
    read; one with an id keeps it."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    path = root / project.path(project.current)
    room = json.loads(path.read_text(encoding="utf-8"))
    room.setdefault("entities", []).extend([{"name": "Old Sign", "x": 64, "y": 96},
                                            {"id": "kept_id", "name": "Kept", "x": 0, "y": 0}])
    path.write_text(json.dumps(room), encoding="utf-8")
    ids = _ids(Project(root, config["world_file"]))
    expected = authoring.ops.make_entity_id(project.current, "Old Sign", 64, 96)
    assert expected in ids and "kept_id" in ids


# --------------------------------------------------------------------- independent review of 58c8d97

def test_studios_door_tool_never_gives_a_deleted_doors_id_to_the_new_door(root: Path, studio: Any) -> None:
    """The AI proposes renaming a door; the person deletes it (and its arrival spot) and links the rooms again from
    the same spot with Studio's door tool. The new door is a different object: the rename doesn't land on it."""
    person, host, _warden = studio
    start = person.project.current
    house = person.project.add_room("House")
    person.project.link_rooms(start, (320, 320), house, (160, 160))
    door = next(e["id"] for e in person.project.scene(start)["entities"] if str(e["id"]).startswith("start_door_to"))
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "rename_entity", "entity_id": door, "name": "Secret Door"}],
                        read["revision"])
    for entity in [e for e in person.project.scene(start)["entities"] if e["id"] != _warden and
                   (e["id"] == door or e.get("spawn_id") or e.get("tag") == "spawn_point")]:
        person.project.edit_scene(lambda room, gone=entity["id"]: authoring.ops.remove_entity(room, gone), start)
    person.project.link_rooms(start, (320, 320), house, (160, 160))
    new_door = next(e["id"] for e in person.project.scene(start)["entities"]
                    if str(e["id"]).startswith("start_door_to"))

    result = host.accept(proposal)

    assert new_door != door, (door, new_door)
    assert result["ok"] is False, result
    assert _entity(person.project, new_door)["name"] != "Secret Door"


def test_a_new_rooms_player_id_is_never_given_to_a_player_placed_after_it_is_deleted(root: Path,
                                                                                    studio: Any) -> None:
    """A new room comes with its own player. The AI proposes moving it; the person deletes it and places a player
    on the same spot: a different object, not moved."""
    person, host, _warden = studio
    cellar = person.project.add_room("Cellar")
    player = next(e["id"] for e in person.project.scene(cellar)["entities"] if e.get("tag") == "player")
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": player, "x": 128, "y": 160,
                                      "room": cellar}], read["revision"])
    person.project.edit_scene(lambda room: authoring.ops.remove_entity(room, player), cellar)
    made = authoring.apply(person.project, [{"op": "place_prefab", "prefab": "player", "x": 128, "y": 128,
                                             "room": cellar}])
    newcomer = str(made["created"][0])

    result = host.accept(proposal)

    assert newcomer != player and result["ok"] is False, (player, newcomer, result)
    moved = next(e for e in person.project.scene(cellar)["entities"] if e["id"] == newcomer)
    assert float(moved["y"]) == 128.0


def test_within_one_batch_an_object_deleted_and_another_placed_on_its_spot_get_different_ids(root: Path,
                                                                                            studio: Any) -> None:
    person, _host, _warden = studio
    made = authoring.apply(person.project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64},
                                            {"op": "remove_entity", "entity_id": "@0"},
                                            {"op": "place_prefab", "prefab": "person", "x": 64, "y": 64}])
    assert made["created"][0] != made["created"][2], made
    with pytest.raises(authoring.ChangeError):  # (so a later "@0" can't land on the second object)
        authoring.apply(person.project, [{"op": "place_prefab", "prefab": "person", "x": 96, "y": 96},
                                         {"op": "remove_entity", "entity_id": "@0"},
                                         {"op": "place_prefab", "prefab": "person", "x": 96, "y": 96},
                                         {"op": "rename_entity", "entity_id": "@0", "name": "Wrong one"}])


def test_an_older_room_read_first_during_an_edit_still_gets_its_usual_ids(root: Path) -> None:
    """Filling in an older room's missing ids doesn't depend on what this session retired: read inside an edit or
    not, it gets the ids it always got (independent review)."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    cellar = project.add_room("Cellar")
    project.save()
    path = root / project.path(cellar)
    room = json.loads(path.read_text(encoding="utf-8"))
    room["entities"].append({"name": "Old Sign", "x": 64, "y": 96})
    path.write_text(json.dumps(room), encoding="utf-8")
    reopened = Project(root, config["world_file"])
    expected = authoring.ops.make_entity_id(cellar, "Old Sign", 64, 96)
    reopened.ids_seen.add(expected)  # (as if an object with that id had been placed and deleted this session)
    with authoring.ops.retired_ids(reopened.ids_seen):
        ids = [str(e["id"]) for e in reopened.scene(cellar)["entities"]]
    assert expected in ids, ids


def test_an_object_in_a_room_first_read_mid_batch_keeps_its_id_from_a_newcomer_in_that_batch(root: Path) -> None:
    """A room first read by a batch (rooms are read when first needed): its object, deleted in that batch, still
    keeps its id from an object the batch then places on its spot."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    cellar = project.add_room("Cellar")
    old = str(authoring.apply(project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64,
                                         "room": cellar}])["created"][0])
    project.save()
    reopened = Project(root, config["world_file"])  # (only the start room read so far)
    assert cellar not in reopened.scenes
    made = authoring.apply(reopened, [{"op": "remove_entity", "entity_id": old, "room": cellar},
                                      {"op": "place_prefab", "prefab": "person", "x": 64, "y": 64, "room": cellar}])
    assert made["created"][1] != old, (old, made)
