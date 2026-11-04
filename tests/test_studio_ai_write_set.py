"""#462 S1: accepting an AI proposal never silently overwrites what the person changed since the AI read the project.

When the person accepts, Studio replays the proposal's operations on the project as it is now. It used to look for
conflicts only between the person's changes and the proposal's *preview* (what the operations changed on the copy the
AI read). An operation also writes values it was given that happened to equal what the AI read: ``move_entity(x=0,
y=100)`` from (0, 0) changes only y in the preview, yet writes x too. If the person had moved the object to (100, 0),
no conflict was found and the replay put x back to 0.

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

pytestmark = pytest.mark.integration  # (a loopback bridge and a real project on disk, as the F6 tests)
ROOM = "packs/core_regions/scenes/start.json"


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window: the project as Studio holds it."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM))
        self.inbox: list[str] = []

    def on_ai_proposal(self, proposal: Any) -> None:
        self.inbox.append(proposal.title)

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

    def pump() -> None:  # Studio's on_update, drained on its own thread here
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


def _at(project: Project, entity_id: str) -> tuple[float, float]:
    found = _entity(project, entity_id)
    return float(found["x"]), float(found["y"])


def _move(project: Project, entity_id: str, x: float, y: float) -> None:
    project.edit_scene(lambda room: authoring.ops.move_entity(room, entity_id, x, y))


def _propose(root: Path, host: StudioAIHost, changes: list[dict[str, Any]], revision: int) -> Any:
    staged = authoring_session.propose(root, changes, base_revision=revision)
    assert staged["ok"], staged
    return next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"])


# --------------------------------------------------------------------- the reported overwrite

def test_a_stale_move_doesn_t_put_back_the_coordinate_the_person_changed(root: Path, studio: Any) -> None:
    """The issue's case: the Warden at (0, 0); the AI proposes move_entity(x=0, y=100); the person moves it to
    (100, 0); accepting must not silently reset x to 0."""
    person, host, warden = studio
    assert _at(person.project, warden) == (0.0, 0.0)
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _move(person.project, warden, 100, 0)
    documents, revision = copy.deepcopy(person.project.all_documents()), person.project.revision

    result = host.accept(proposal)

    assert _at(person.project, warden) == (100.0, 0.0), "the person's x survives"
    assert result["ok"] is False and result["reason"] == "conflict", result
    assert person.project.all_documents() == documents and person.project.revision == revision, "nothing applied"
    assert proposal.status == "conflict"


def test_an_edit_the_proposal_doesnt_write_still_lets_it_apply(root: Path, studio: Any) -> None:
    """Legitimate concurrent work: the person renames the Warden; the AI's move doesn't write its name. Both land."""
    person, host, warden = studio
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    person.project.edit_scene(lambda room: authoring.ops.rename_entity(room, warden, "Keeper"))

    result = host.accept(proposal)

    assert result["ok"] is True, result
    assert _at(person.project, warden) == (0.0, 100.0) and _entity(person.project, warden)["name"] == "Keeper"


# --------------------------------------------------------------------- batches, created objects, repeats

def _place(project: Project, name: str, x: float, y: float) -> str:
    made = authoring.apply(project, [{"op": "place_prefab", "prefab": "person", "x": x, "y": y},
                                     {"op": "rename_entity", "entity_id": "@0", "name": name}])
    return str(made["created"][0])


def test_a_batch_is_refused_whole_if_any_of_its_writes_lands_on_the_persons_edit(root: Path, studio: Any) -> None:
    """The first operation is safe on its own; the second writes the x the person changed: nothing at all applies."""
    person, host, warden = studio
    scout = _place(person.project, "Scout", 300, 300)
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": scout, "x": 320, "y": 300},
                                     {"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _move(person.project, warden, 100, 0)
    before = copy.deepcopy(person.project.all_documents())

    result = host.accept(proposal)

    assert result["ok"] is False and result["reason"] == "conflict"
    assert person.project.all_documents() == before, "not even the safe first move"
    (clash,) = result["conflicts"]
    assert clash["path"].endswith(f"#{warden}/x") and (clash["base"], clash["studio"], clash["ai"]) == (0.0, 100.0, 0.0)


def test_repeated_writes_in_a_batch_are_judged_by_what_the_batch_finally_writes(root: Path, studio: Any) -> None:
    """Two moves in one batch: the last one counts. With the person's rename it applies; with their move it clashes."""
    person, host, warden = studio
    read = authoring_session.read_project(root)
    batch = [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 50},
             {"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}]
    clean = _propose(root, host, batch, read["revision"])
    person.project.edit_scene(lambda room: authoring.ops.rename_entity(room, warden, "Keeper"))
    assert host.accept(clean)["ok"] is True and _at(person.project, warden) == (0.0, 100.0)

    read = authoring_session.read_project(root)
    clash = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 150},
                                  {"op": "move_entity", "entity_id": warden, "x": 0, "y": 200}], read["revision"])
    _move(person.project, warden, 100, 100)
    assert host.accept(clash)["reason"] == "conflict" and _at(person.project, warden) == (100.0, 100.0)


def test_objects_the_batch_creates_and_refers_to_land_beside_the_persons_new_ones(root: Path, studio: Any) -> None:
    """The AI places an NPC and names it through "@0"; meanwhile the person placed one of their own. Both stay,
    each as made: the new id the batch gets now isn't one of the person's, and nothing of theirs is touched."""
    person, host, _warden = studio
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "place_prefab", "prefab": "person", "x": 400, "y": 64},
                                     {"op": "rename_entity", "entity_id": "@0", "name": "Ranger"}], read["revision"])
    mine = _place(person.project, "Gardener", 200, 64)
    theirs_before = copy.deepcopy(_entity(person.project, mine))

    result = host.accept(proposal)

    assert result["ok"] is True, result
    made = str(proposal.created[0])
    assert made != mine and _entity(person.project, made)["name"] == "Ranger"
    assert _entity(person.project, mine) == theirs_before


def test_a_proposal_is_applied_once_and_a_conflict_clears_when_the_person_puts_things_back(root: Path,
                                                                                          studio: Any) -> None:
    person, host, warden = studio
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _move(person.project, warden, 100, 0)
    assert host.accept(proposal)["reason"] == "conflict"
    _move(person.project, warden, 0, 0)  # the person moves it back: the proposal no longer writes over anything
    assert host.accept(proposal)["ok"] is True and _at(person.project, warden) == (0.0, 100.0)
    revision = person.project.revision
    again = host.accept(proposal)
    assert again["ok"] is False and again["reason"] == "accepted" and person.project.revision == revision


def test_the_same_result_both_ways_isnt_a_conflict(root: Path, studio: Any) -> None:
    person, host, warden = studio
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _move(person.project, warden, 0, 100)
    assert host.accept(proposal)["ok"] is True and _at(person.project, warden) == (0.0, 100.0)


# --------------------------------------------------------------------- undo, save, reopen, failure part-way

def test_a_refusal_leaves_undo_and_saving_as_they_were_and_an_acceptance_is_one_undo_step(root: Path,
                                                                                        studio: Any) -> None:
    person, host, warden = studio
    read = authoring_session.read_project(root)
    stale = _propose(root, host, [{"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    _move(person.project, warden, 100, 0)
    dirty = person.project.is_dirty
    assert host.accept(stale)["reason"] == "conflict" and person.project.is_dirty == dirty
    assert person.project.undo() and _at(person.project, warden) == (0.0, 0.0), "undo takes back the person's move"
    assert person.project.redo() and _at(person.project, warden) == (100.0, 0.0)
    host.reject_proposal(stale)

    read = authoring_session.read_project(root)
    rename = _propose(root, host, [{"op": "rename_entity", "entity_id": warden, "name": "Keeper"}], read["revision"])
    _move(person.project, warden, 150, 0)
    assert host.accept(rename)["ok"] is True
    assert person.project.undo() and _entity(person.project, warden)["name"] == "Warden"
    assert _at(person.project, warden) == (150.0, 0.0), "one undo step: the AI's rename, not the person's move"
    assert person.project.redo() and _entity(person.project, warden)["name"] == "Keeper"
    person.project.save()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    on_disk = _entity(Project(root, config["world_file"]), warden)
    assert on_disk["name"] == "Keeper" and (float(on_disk["x"]), float(on_disk["y"])) == (150.0, 0.0)


def test_a_failure_part_way_through_applying_changes_nothing(root: Path, studio: Any,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """Fault injection: the second operation fails while the batch is really applied (after the checks passed)."""
    person, host, warden = studio
    scout = _place(person.project, "Scout", 300, 300)
    read = authoring_session.read_project(root)
    proposal = _propose(root, host, [{"op": "move_entity", "entity_id": scout, "x": 320, "y": 300},
                                     {"op": "move_entity", "entity_id": warden, "x": 0, "y": 100}], read["revision"])
    person.project.edit_scene(lambda room: authoring.ops.rename_entity(room, warden, "Keeper"))
    before, revision = copy.deepcopy(person.project.all_documents()), person.project.revision
    real = authoring._apply_one

    def failing(project: Any, index: int, change: Any, created: Any) -> Any:
        if project is person.project and index == 1:
            raise authoring.ChangeError(index, "move_entity", "injected failure")
        return real(project, index, change, created)

    monkeypatch.setattr(authoring, "_apply_one", failing)
    result = host.accept(proposal)

    assert result["ok"] is False and "injected failure" in result["message"]
    assert person.project.all_documents() == before and person.project.revision == revision
    assert proposal.status == "failed"


# --------------------------------------------------------------------- the river editor

def test_river_settings_the_proposal_doesnt_write_survive_and_ones_it_does_clash(root: Path, studio: Any) -> None:
    person, host, _warden = studio

    def hd2d(room: dict[str, Any]) -> dict[str, Any]:
        room = copy.deepcopy(room)
        room.setdefault("settings", {})["hd2d"] = {
            "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [1600, 1200]}}
        return authoring.ops.add_river(room, "brook", [[4.0, 600.0, 64.0, -8.0], [1596.0, 600.0, 64.0, -8.0]])

    def river() -> dict[str, Any]:
        return person.project.scene()["settings"]["hd2d"]["rivers"][0]

    person.project.edit_scene(hd2d)
    read = authoring_session.read_project(root)
    wade = _propose(root, host, [{"op": "set_river", "river_id": "brook", "passable": "wade"}], read["revision"])
    person.project.edit_scene(lambda room: authoring.ops.set_river(room, "brook", flow=2.5))
    assert host.accept(wade)["ok"] is True
    assert river()["passable"] == "wade" and river()["flow"] == 2.5, "both kept"

    read = authoring_session.read_project(root)
    faster = _propose(root, host, [{"op": "set_river", "river_id": "brook", "flow": 3.0}], read["revision"])
    person.project.edit_scene(lambda room: authoring.ops.set_river(room, "brook", flow=1.5))
    assert host.accept(faster)["reason"] == "conflict" and river()["flow"] == 1.5


# --------------------------------------------------------------------- the check itself

def test_overwrites_finds_the_same_path_and_one_inside_the_other_but_not_neighbours() -> None:
    base = {"rooms": {"r": {"entities": [{"id": "e", "x": 0, "y": 0, "props": {"hp": 3}}]}}}
    e = ("rooms", "r", "entities", "#e")
    ours = {e + ("x",): (0, 100), e + ("props",): ({"hp": 3}, None)}  # the person moved it and cleared its props
    writes = {e + ("x",): (100, 0),  # the same path: over the person's x
              e + ("y",): (0, 100),  # a neighbour: fine
              e + ("props", "hp"): (None, 5),  # inside what the person changed
              ("rooms", "r", "name"): ("a", "b")}  # elsewhere: fine
    found = {c["path"]: c for c in authoring.overwrites(ours, writes, base)}
    assert set(found) == {"rooms/r/entities/#e/x", "rooms/r/entities/#e/props/hp"}
    assert (found["rooms/r/entities/#e/x"]["base"], found["rooms/r/entities/#e/x"]["studio"],
            found["rooms/r/entities/#e/x"]["ai"]) == (0, 100, 0)
    assert found["rooms/r/entities/#e/props/hp"]["base"] == 3
    # what the proposal writes holds what the person changed (it replaces the whole object): a conflict too
    assert [c["path"] for c in authoring.overwrites({e + ("x",): (0, 100)}, {e: ({}, None)}, base)] == \
        ["rooms/r/entities/#e"]
    assert authoring.overwrites({}, writes, base) == [] and authoring.overwrites(ours, {}, base) == []
