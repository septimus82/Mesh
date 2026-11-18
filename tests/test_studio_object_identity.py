"""#462 R3: a structure, a river or a conversation line deleted in Mesh Studio never gives its id to the one made next.

Astra's three reproductions. An AI reads the project and proposes a change to one object; the person deletes that
object and makes another of the same kind; the replacement got the deleted one's id (a structure from its model's
name, a river drawn in Studio "river"/"river-2", a line the next ``line_N``), so accepting the old proposal changed
the replacement: the person approved a change to an object they had since deleted, and it landed on a different one.

Ordinary objects already never reuse an id within a session (#462 S1-ID: ``Project.ids_seen``,
``project_ops.retired_ids``). The same set now remembers structures and rivers per room and lines per conversation
(room and object), and the ids those three kinds are given avoid it: a new one never takes an id one of its kind had
this session, and an explicitly given id that one had is refused. The shared player's conversation is one in every room
(rooms hold a reference to the player; ``Project.player`` holds what it says), so its lines are remembered once, for
the whole project.

Each test runs a real StudioAIHost on its loopback bridge; the AI goes through ``authoring_session`` (what the MCP
tools and ``mesh author`` call) with R1's ``base_revision_id``; the person edits with the operations Studio's own
tools call, through ``Project.edit_scene`` as they do; acceptance is ``StudioAIHost.accept``, as Studio's Accept.
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
from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project
from engine.studio_river import RiverTool

pytestmark = pytest.mark.integration  # (F13-A, #422: bridges; every default run has it)
MODEL = "assets/models/crate.glb"
COURSE = [[200.0, 900.0, 48.0, 24.0], [700.0, 900.0, 48.0, 24.0]]
ELSEWHERE = [[200.0, 1300.0, 48.0, 24.0], [700.0, 1300.0, 48.0, 24.0]]


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window: the project as Studio holds it."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=""))
        self.inbox: list[str] = []

    def on_ai_proposal(self, proposal: Any) -> None:
        self.inbox.append(proposal.title)

    def on_ai_decided(self, proposal: Any) -> None:
        pass


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="hd2d_rpg")  # (an HD-2D village: structures, people who talk)
    return path


@pytest.fixture
def studio(root: Path) -> Iterator[tuple[_Studio, StudioAIHost]]:
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    person = _Studio(Project(root, config["world_file"]))
    host = StudioAIHost(person)
    host.start()
    stop = threading.Event()

    def pump() -> None:  # Studio's on_update, drained on its own thread here
        while not stop.is_set():
            host.drain()
            time.sleep(0.01)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    yield person, host
    stop.set()
    thread.join(timeout=2)
    host.stop()


def _propose(root: Path, host: StudioAIHost, changes: list[dict[str, Any]]) -> Any:
    """The AI reads the project and proposes ``changes`` against what it read (R1's revision identity)."""
    read = authoring_session.read_project(root)
    staged = authoring_session.propose(root, changes, title="An AI's change", base_revision_id=read["revision_id"])
    assert staged["ok"], staged
    return next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"])


def _structure(project: Project, sid: str) -> dict[str, Any] | None:
    return ops.find_structure(project.scene(), sid)


def _river_tool(project: Project) -> Any:
    """Studio's river tool, as far as choosing a new river's id goes (``RiverTool._new_id``)."""
    tool = SimpleNamespace(studio=SimpleNamespace(project=project))
    tool.saved = lambda: ops.rivers(project.scene())
    return tool


def _draw_river(project: Project, points: list[list[float]]) -> str:
    """The person draws a river with Studio's river tool: its id as the tool chooses it, added as it adds it."""
    rid = RiverTool._new_id(_river_tool(project))
    project.edit_scene(lambda s: ops.add_river(s, rid, copy.deepcopy(points), flow=1.0))
    return str(rid)


def _rivers(project: Project) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in ops.rivers(project.scene())}


def _talker(project: Project) -> str:
    return next(e["id"] for e in project.scene()["entities"] if "Dialogue" in (e.get("behaviours") or []))


def _lines(project: Project, entity_id: str) -> dict[str, dict[str, Any]]:
    return ops.conversation(ops.find_entity(project.scene(), entity_id))["nodes"]


def _add_line(project: Project, entity_id: str, text: str) -> str:
    """The person adds a line in Studio's conversation editor ("+ Next line") and writes it."""
    made: list[str] = []

    def change(scene: dict[str, Any]) -> dict[str, Any]:
        out, node_id = ops.add_line(scene, entity_id, text="...")
        made.append(node_id)
        return out

    project.edit_scene(change)
    project.edit_scene(lambda s: ops.set_line(s, entity_id, made[0], text=text))
    return made[0]


def _everything_but(project: Project, kind: str) -> Any:
    """The project's documents with the one kind of thing a test changes taken out: equal before and after means
    nothing else was changed."""
    docs = copy.deepcopy(project.all_documents())
    if kind == "dialogue" and isinstance(docs.get("player"), dict):  # (the shared player's conversation)
        (docs["player"].get("behaviour_config") or {}).pop("Dialogue", None)
    for room in docs["rooms"].values():
        hd2d = (room.get("settings") or {}).get("hd2d") or {}
        if kind in ("structures", "rivers"):
            hd2d.pop(kind, None)
        else:
            for entity in room.get("entities") or []:
                (entity.get("behaviour_config") or {}).pop("Dialogue", None)
    return docs


def _refused_or_conflict(result: dict[str, Any]) -> None:
    assert result["ok"] is False and result["reason"] in ("conflict", "invalid_change"), result


# ---------------------------------------------------------------- the three reproductions
def test_a_stale_proposal_about_a_deleted_structure_never_lands_on_its_replacement(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    sid: list[str] = []

    def place(scene: dict[str, Any], x: float) -> dict[str, Any]:  # (Studio's structure tool: model, spot, no id)
        out, made = ops.place_structure(scene, MODEL, x, 900.0)
        sid.append(made)
        return out

    project.edit_scene(lambda s: place(s, 400.0))
    original = sid[0]
    turn = _propose(root, host, [{"op": "set_structure", "structure_id": original, "rotation": 90}])
    assert any(original in line for line in turn.summary), turn.summary  # the preview is about this structure
    project.edit_scene(lambda s: ops.remove_structure(s, original))  # the person deletes it ...
    project.edit_scene(lambda s: place(s, 1200.0))  # ... and places another crate elsewhere
    replacement = sid[1]
    assert replacement != original, "the replacement was given the deleted structure's id"
    placed, others = copy.deepcopy(_structure(project, replacement)), _everything_but(project, "structures")

    _refused_or_conflict(host.accept(turn))  # the old proposal: refused, never applied to the replacement
    assert _structure(project, replacement) == placed and _structure(project, original) is None
    assert _everything_but(project, "structures") == others
    fresh = _propose(root, host, [{"op": "set_structure", "structure_id": replacement, "rotation": 90}])
    assert host.accept(fresh)["ok"] and _structure(project, replacement)["rotation"] == 90.0  # asked anew: fine


def test_a_stale_proposal_about_a_deleted_river_never_lands_on_its_replacement(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    original = _draw_river(project, COURSE)
    block = _propose(root, host, [{"op": "set_river", "river_id": original, "passable": "block"}])
    project.edit_scene(lambda s: ops.remove_river(s, original))  # the person removes it ...
    replacement = _draw_river(project, ELSEWHERE)  # ... and draws another, elsewhere
    assert replacement != original, "the replacement river was given the deleted river's id"
    drawn, others = copy.deepcopy(_rivers(project)[replacement]), _everything_but(project, "rivers")

    _refused_or_conflict(host.accept(block))
    assert _rivers(project) == {replacement: drawn} and _everything_but(project, "rivers") == others
    fresh = _propose(root, host, [{"op": "set_river", "river_id": replacement, "passable": "block"}])
    assert host.accept(fresh)["ok"] and _rivers(project)[replacement]["passable"] == "block"


def test_a_stale_proposal_about_a_deleted_line_never_lands_on_its_replacement(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    talker = _talker(project)
    original = _add_line(project, talker, "The bridge is out.")  # (a line of its own: the last one, numbered last)
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": talker, "node_id": original, "speaker": "Ghost"}])
    project.edit_scene(lambda s: ops.remove_line(s, talker, original))  # the person deletes the line ...
    replacement = _add_line(project, talker, "The ferry runs at dawn.")  # ... and writes another
    assert replacement != original, "the replacement line was given the deleted line's id"
    written, others = copy.deepcopy(_lines(project, talker)), _everything_but(project, "dialogue")

    _refused_or_conflict(host.accept(ghost))
    assert _lines(project, talker) == written and "speaker" not in written[replacement]
    assert written[replacement]["text"] == "The ferry runs at dawn." and _everything_but(project, "dialogue") == others
    fresh = _propose(root, host, [{"op": "set_line", "entity_id": talker, "node_id": replacement, "speaker": "Ghost"}])
    assert host.accept(fresh)["ok"] and _lines(project, talker)[replacement]["speaker"] == "Ghost"


# ---------------------------------------------------------------- every way one is made
def _place(project: Project, x: float = 400.0, key: str | None = None) -> str:
    """The person places a crate with Studio's structure tool (no id given): its id."""
    made: list[str] = []

    def change(scene: dict[str, Any]) -> dict[str, Any]:
        out, sid = ops.place_structure(scene, MODEL, x, 900.0)
        made.append(sid)
        return out

    project.edit_scene(change, key)
    return made[0]


def _stage(root: Path, changes: list[dict[str, Any]]) -> dict[str, Any]:
    read = authoring_session.read_project(root)
    return authoring_session.propose(root, changes, title="An AI's batch", base_revision_id=read["revision_id"])


def test_deleting_and_making_again_never_gives_an_id_back(studio: Any) -> None:
    person, _host = studio
    project = person.project
    talker = _talker(project)
    made: dict[str, list[str]] = {"structure": [], "river": [], "line": []}
    for cycle in range(4):
        sid = _place(project)
        project.edit_scene(lambda s, sid=sid: ops.remove_structure(s, sid))
        rid = _draw_river(project, COURSE)
        project.edit_scene(lambda s, rid=rid: ops.remove_river(s, rid))
        lid = _add_line(project, talker, f"Line {cycle}")
        project.edit_scene(lambda s, lid=lid: ops.remove_line(s, talker, lid))
        made["structure"].append(sid), made["river"].append(rid), made["line"].append(lid)
    assert all(len(set(ids)) == 4 for ids in made.values()), made
    assert made["river"] == ["river", "river-2", "river-3", "river-4"]  # (named as the tool names them)


def test_a_batch_that_makes_removes_and_makes_again_gets_new_ids_and_its_preview_names_them(root: Path,
                                                                                           studio: Any) -> None:
    person, host = studio
    project = person.project
    talker = _talker(project)
    batch = [{"op": "place_structure", "model": MODEL, "x": 400, "y": 900},
             {"op": "remove_structure", "structure_id": "@0"},
             {"op": "place_structure", "model": MODEL, "x": 400, "y": 900},
             {"op": "add_line", "entity_id": talker, "text": "One"},
             {"op": "remove_line", "entity_id": talker, "node_id": "@3"},
             {"op": "add_line", "entity_id": talker, "text": "Two"}]
    staged = _stage(root, batch)
    assert staged["ok"], staged
    proposal = next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"])
    accepted = host.accept(proposal)
    assert accepted["ok"], accepted
    created = accepted["created"]
    assert created[0] != created[2] and created[3] != created[5], created  # never one id for two things
    preview = " ".join(staged["proposal"]["summary"])
    assert created[2] in preview and created[5] in preview  # the preview named what accepting made
    assert _structure(project, created[2]) is not None and _structure(project, created[0]) is None
    assert _lines(project, talker)[created[5]]["text"] == "Two" and created[3] not in _lines(project, talker)

    for again in ([{"op": "add_river", "river_id": "brook", "points": COURSE},
                   {"op": "remove_river", "river_id": "brook"},
                   {"op": "add_river", "river_id": "brook", "points": ELSEWHERE}],
                  [{"op": "place_structure", "model": MODEL, "x": 400, "y": 900, "structure_id": "tower"},
                   {"op": "remove_structure", "structure_id": "tower"},
                   {"op": "place_structure", "model": MODEL, "x": 800, "y": 900, "structure_id": "tower"}]):
        refused = _stage(root, again)  # an id given again in one batch: refused, nothing staged
        assert refused["ok"] is False and refused["reason"] == "invalid_change" and refused["index"] == 2, refused
        assert "earlier in this session" in refused["message"]
    assert len(host.pending()) == 0


def test_studio_and_an_ai_never_give_each_other_an_id_back(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    drawn = _draw_river(project, COURSE)  # Studio's river tool: "river"
    project.edit_scene(lambda s: ops.remove_river(s, drawn))
    refused = _stage(root, [{"op": "add_river", "river_id": drawn, "points": ELSEWHERE}])  # the AI can't take it
    assert refused["reason"] == "invalid_change" and "earlier in this session" in refused["message"]
    staged = _stage(root, [{"op": "add_river", "river_id": "river-2", "points": ELSEWHERE}])
    assert host.accept(next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"]))["ok"]
    project.edit_scene(lambda s: ops.remove_river(s, "river-2"))
    assert _draw_river(project, COURSE) == "river-3"  # nor the tool the AI's

    staged = _stage(root, [{"op": "place_structure", "model": MODEL, "x": 1200, "y": 900}])  # (off the river)
    assert staged["ok"], staged
    accepted = host.accept(next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"]))
    ai_made = accepted["created"][0]
    project.edit_scene(lambda s: ops.remove_structure(s, ai_made))
    assert _place(project, 1200.0) != ai_made  # Studio's tool never takes what the AI's change made


def test_look_alikes_stay_apart(root: Path, studio: Any) -> None:
    """Two crates on one spot, two lines with the same words: different things, and a change to one never lands on the
    other, even once the first is gone."""
    person, host = studio
    project = person.project
    first, second = _place(project), _place(project)
    assert first != second and {k: v for k, v in _structure(project, first).items() if k != "id"} == {
        k: v for k, v in _structure(project, second).items() if k != "id"}
    turn = _propose(root, host, [{"op": "set_structure", "structure_id": first, "rotation": 45}])
    project.edit_scene(lambda s: ops.remove_structure(s, first))
    kept = copy.deepcopy(_structure(project, second))
    _refused_or_conflict(host.accept(turn))
    assert _structure(project, second) == kept

    talker = _talker(project)
    one, two = _add_line(project, talker, "Hello."), _add_line(project, talker, "Hello.")
    assert one != two
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": talker, "node_id": one, "speaker": "Ghost"}])
    project.edit_scene(lambda s: ops.remove_line(s, talker, one))
    _refused_or_conflict(host.accept(ghost))
    assert "speaker" not in _lines(project, talker)[two]


def test_undo_brings_the_same_object_back_and_redo_never_frees_its_id(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    original = _place(project)
    turn = _propose(root, host, [{"op": "set_structure", "structure_id": original, "rotation": 90}])
    project.edit_scene(lambda s: ops.remove_structure(s, original))
    assert project.undo() and _structure(project, original) is not None  # the deleted crate itself, back
    assert host.accept(turn)["ok"] and _structure(project, original)["rotation"] == 90.0  # it is what was previewed
    assert project.undo() and project.redo()  # (the turn again)
    project.edit_scene(lambda s: ops.remove_structure(s, original))
    assert project.undo() and project.redo() and _structure(project, original) is None  # deleted again
    assert _place(project) != original  # and its id still isn't free

    made = _place(project, 900.0)  # a crate placed and undone: its id isn't given to the next one either
    assert project.undo() and _structure(project, made) is None
    assert _place(project, 900.0) not in (made, original)


def test_a_preview_names_the_ids_that_accepting_makes(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    talker = _talker(project)
    changes = [{"op": "place_structure", "model": MODEL, "x": 400, "y": 900},
               {"op": "add_line", "entity_id": talker, "text": "Hm."}]
    _before, after = authoring.dry_run(project, changes)  # (Studio's preview: a copy, its ids as the edit's)
    staged = _stage(root, changes)
    accepted = host.accept(next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"]))
    sid, lid = accepted["created"][0], accepted["created"][1]
    room = after["rooms"][project.current]
    assert ops.find_structure(room, sid) is not None
    assert lid in ops.conversation(ops.find_entity(room, talker))["nodes"]


def test_saving_and_opening_again_keeps_every_id(root: Path, studio: Any) -> None:
    person, _host = studio
    project = person.project
    talker = _talker(project)
    sid, rid, lid = _place(project), _draw_river(project, COURSE), _add_line(project, talker, "Saved.")
    project.save()
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    reopened = Project(root, config["world_file"])  # (another session: what was saved, with its ids, as it was)
    assert reopened.all_documents()["rooms"] == project.all_documents()["rooms"]
    assert ops.find_structure(reopened.scene(), sid) and rid in _rivers(reopened) and lid in _lines(reopened, talker)
    assert Project(root, config["world_file"]).all_documents() == reopened.all_documents()  # (loading makes no ids)
    assert _place(reopened) != sid and _draw_river(reopened, ELSEWHERE) != rid


def test_an_older_conversation_is_brought_up_to_date_exactly_as_before(studio: Any) -> None:
    """A conversation saved as one list of lines (before lines had ids) becomes a chain of numbered lines the first
    time it is edited: the same ids in Studio as anywhere else, whatever Studio has seen."""
    person, _host = studio
    project = person.project
    talker = _talker(project)

    def legacy(scene: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(scene)
        entity = ops.find_entity(out, talker)
        entity["behaviour_config"]["Dialogue"] = {"dialogue_lines": ["Hello.", "Mind the bridge."], "once": False}
        return out

    project.edit_scene(legacy)
    plain, plain_id = ops.add_line(copy.deepcopy(project.scene()), talker, text="Bye.")  # (outside Studio's edits)
    assert _add_line(project, talker, "Bye.") == plain_id
    assert _lines(project, talker) == ops.conversation(ops.find_entity(plain, talker))["nodes"] | {
        plain_id: {"text": "Bye."}}


def test_each_conversation_and_each_room_numbers_its_own(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    talkers = [e["id"] for e in project.scene()["entities"] if "Dialogue" in (e.get("behaviours") or [])][:2]
    gone = _add_line(project, talkers[0], "Gone soon.")
    project.edit_scene(lambda s: ops.remove_line(s, talkers[0], gone))
    expected = ops.add_line(copy.deepcopy(project.scene()), talkers[1], text="Mine.")[1]  # (its own lines only)
    assert _add_line(project, talkers[1], "Mine.") == expected  # another conversation may have a line_2 too

    cottage = next(k for k, _l, _p in project.rooms() if k != project.current)  # (a room not read yet)
    staged = _stage(root, [{"op": "place_structure", "model": MODEL, "x": 160, "y": 160, "room": cottage}])
    accepted = host.accept(next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"]))
    assert accepted["created"][0] == "crate"  # no crate there yet: the start room's crates are another room's
    project.edit_scene(lambda s: ops.remove_structure(s, "crate"), cottage)
    refused = _stage(root, [{"op": "place_structure", "model": MODEL, "x": 160, "y": 160, "room": cottage,
                             "structure_id": "crate"}])
    assert refused["reason"] == "invalid_change" and "earlier in this session" in refused["message"]
    assert _stage(root, [{"op": "place_structure", "model": MODEL, "x": 160, "y": 160,
                          "structure_id": "tower"}])["ok"]  # (an id no structure of this room had: fine)


@pytest.mark.parametrize("change", [
    {"op": "place_structure", "model": MODEL, "x": 400, "y": 900, "structure_id": "Bad Id!"},
    {"op": "place_structure", "model": MODEL, "x": 400, "y": 900, "structure_id": 5},
    {"op": "place_structure", "model": MODEL, "x": 400, "y": 900, "structure_id": "x" * 41},
    {"op": "add_river", "river_id": "", "points": COURSE},
    {"op": "add_river", "river_id": "Bad Id!", "points": COURSE},
], ids=["structure: not a short name", "structure: a number", "structure: too long", "river: empty",
        "river: not a short name"])
def test_an_id_that_isnt_one_is_refused(root: Path, studio: Any, change: dict[str, Any]) -> None:
    person, host = studio
    documents = copy.deepcopy(person.project.all_documents())
    refused = _stage(root, [change])
    assert refused["ok"] is False and refused["reason"] == "invalid_change", refused
    assert host.pending() == [] and person.project.all_documents() == documents


def test_a_conversation_made_again_never_gets_its_old_opening_lines_id(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    talker = _talker(project)
    opening = ops.conversation(ops.find_entity(project.scene(), talker))["start"]
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": talker, "node_id": opening, "speaker": "Ghost"}])
    project.edit_scene(lambda s: ops.remove_behaviour(s, talker, "Dialogue"))  # the conversation goes ...
    project.edit_scene(lambda s: ops.add_behaviour(s, talker, "Dialogue"))  # ... a new one starts: its first words
    project.edit_scene(lambda s: ops.set_dialogue_text(s, talker, "A new beginning."))
    lines = _lines(project, talker)
    assert opening not in lines and list(lines.values()) == [{"text": "A new beginning."}]
    _refused_or_conflict(host.accept(ghost))
    assert _lines(project, talker) == lines


def test_a_revision_of_another_session_is_still_refused(root: Path, studio: Any) -> None:
    person, _host = studio
    read = authoring_session.read_project(root)
    session = person.project.session
    other = ("e" if session[0] == "f" else "f") + session[1:] + read["revision_id"][len(session):]
    refused = authoring_session.propose(root, [{"op": "set_structure", "structure_id": "crate_1", "rotation": 5}],
                                        base_revision_id=other)
    assert refused["reason"] == "revision_from_another_session" and person.inbox == []



# ---------------------------------------------------------------- the shared player's conversation
def _player(project: Project, key: str | None = None) -> str:
    """The shared player's object in a room (each room has its own reference, with its own id)."""
    return project.shared_players(key or project.current)[0]


def _player_lines(project: Project, key: str | None = None) -> dict[str, dict[str, Any]]:
    return ops.conversation(ops.find_entity(project.scene(key), _player(project, key)))["nodes"]


def _add_player_line(project: Project, key: str, text: str) -> str:
    """The person selects the player in room ``key`` and adds a line in Studio's conversation editor."""
    made: list[str] = []

    def change(scene: dict[str, Any]) -> dict[str, Any]:
        out, node_id = ops.add_line(scene, _player(project, key), text="...")
        made.append(node_id)
        return out

    project.edit_scene(change, key)
    project.edit_scene(lambda s: ops.set_line(s, _player(project, key), made[0], text=text), key)
    return made[0]


def _remove_player_line(project: Project, key: str, node_id: str) -> None:
    project.edit_scene(lambda s: ops.remove_line(s, _player(project, key), node_id), key)


def _talking_player(project: Project) -> tuple[str, str]:
    """The person gives the player its first words, in the start room: ``(start room, another room)``."""
    start = project.current
    project.edit_scene(lambda s: ops.set_dialogue_text(s, _player(project), "Morning."))
    return start, next(k for k, _l, _p in project.rooms() if k != start)


def _everywhere(project: Project) -> list[dict[str, dict[str, Any]]]:
    return [_player_lines(project, key) for key, _l, _p in project.rooms()]


def _npc(project: Project) -> str:
    return next(e["id"] for e in project.scene()["entities"]
                if "Dialogue" in (e.get("behaviours") or []) and not project.is_shared_player(e["id"]))


@pytest.mark.parametrize("elsewhere", [False, True], ids=["written in the same room", "written in another room"])
def test_a_stale_proposal_about_a_deleted_player_line_never_lands_on_its_replacement(root: Path, studio: Any,
                                                                                    elsewhere: bool) -> None:
    person, host = studio
    project = person.project
    start, other = _talking_player(project)
    where = other if elsewhere else start
    original = _add_player_line(project, start, "The bridge is out.")
    assert original == "line_2"
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": _player(project), "node_id": original,
                                   "speaker": "Ghost"}])
    _remove_player_line(project, start, original)  # the person deletes the player's line ...
    replacement = _add_player_line(project, where, "The ferry runs at dawn.")  # ... and writes another
    assert replacement != original, "the player's replacement line was given the deleted line's id"
    written, others = copy.deepcopy(_player_lines(project, where)), _everything_but(project, "dialogue")

    _refused_or_conflict(host.accept(ghost))
    assert _everywhere(project) == [written, written] and "speaker" not in written[replacement]
    assert _everything_but(project, "dialogue") == others
    fresh = _propose(root, host, [{"op": "set_line", "entity_id": _player(project, other), "node_id": replacement,
                                   "speaker": "Ghost", "room": other}])  # (made in the other room: every room's)
    assert host.accept(fresh)["ok"]
    assert all(lines[replacement]["speaker"] == "Ghost" for lines in _everywhere(project))


def test_the_players_lines_have_one_history_in_every_room_through_undo_and_redo(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    npc = _npc(project)
    start, other = _talking_player(project)
    made = []
    for cycle in range(4):  # written in one room, deleted in the other
        here, there = (start, other) if cycle % 2 == 0 else (other, start)
        made.append(_add_player_line(project, here, f"Line {cycle}"))
        _remove_player_line(project, there, made[-1])
    assert made == ["line_2", "line_3", "line_4", "line_5"]

    kept = _add_player_line(project, other, "Keep me.")
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": _player(project), "node_id": kept,
                                   "speaker": "Ghost"}])
    _remove_player_line(project, start, kept)
    assert project.undo() and all(kept in lines for lines in _everywhere(project))  # the deleted line itself, back
    assert host.accept(ghost)["ok"]  # it is what was previewed
    assert all(lines[kept]["speaker"] == "Ghost" for lines in _everywhere(project))
    _remove_player_line(project, other, kept)
    assert project.undo() and project.redo() and not any(kept in lines for lines in _everywhere(project))
    following = _add_player_line(project, start, "Next.")
    assert following not in (*made, kept)  # redo never freed its id
    alone: list[str] = []

    def add_only(scene: dict[str, Any]) -> dict[str, Any]:  # (one edit: the line made, then that edit undone)
        out, node_id = ops.add_line(scene, _player(project, start), text="Gone.")
        alone.append(node_id)
        return out

    project.edit_scene(add_only, start)
    assert project.undo() and not any(alone[0] in lines for lines in _everywhere(project))
    assert _add_player_line(project, other, "Instead.") not in (*made, kept, following, alone[0])  # nor undoing it

    expected = ops.add_line(copy.deepcopy(project.scene()), npc, text="Mine.")[1]  # (another object's: its own)
    assert _add_line(project, npc, "Mine.") == expected


def test_an_ai_batch_on_the_players_lines_gets_new_ids_and_its_preview_names_them(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    start, other = _talking_player(project)
    batch = [{"op": "add_line", "entity_id": _player(project, other), "text": "One", "room": other},
             {"op": "remove_line", "entity_id": _player(project, other), "node_id": "@0", "room": other},
             {"op": "add_line", "entity_id": _player(project), "text": "Two"}]
    _before, after = authoring.dry_run(project, batch)  # (Studio's preview: a copy, its ids as the edit's)
    staged = _stage(root, batch)
    assert staged["ok"], staged
    accepted = host.accept(next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"]))
    assert accepted["ok"], accepted
    created = accepted["created"]
    assert created[0] != created[2], created  # never one id for two lines
    previewed = after["player"]["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]
    assert previewed[created[2]]["text"] == "Two" and created[0] not in previewed
    assert _everywhere(project) == [previewed, previewed]


def test_saving_and_opening_again_keeps_the_players_lines(root: Path, studio: Any) -> None:
    person, _host = studio
    project = person.project
    start, other = _talking_player(project)
    kept = _add_player_line(project, other, "Saved.")
    project.save()
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    reopened = Project(root, world_file)  # (another session: the player as saved, its lines' ids as they were)
    assert reopened.player == project.player and kept in _player_lines(reopened, start)
    assert Project(root, world_file).player == reopened.player  # (loading makes no ids)
    _remove_player_line(reopened, start, kept)  # a line as saved, deleted in the new session ...
    assert _add_player_line(reopened, other, "More.") not in ("root", kept)  # ... isn't given to the next one


def test_a_room_with_its_own_player_numbers_its_lines_as_any_conversation(root: Path) -> None:
    """A project made before the player was shared: a room's own full player is an object like any other, and its
    conversation's lines are remembered for that room and object."""
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    shared = Project(root, world_file)
    start = shared.current
    room_file = root / shared.path(start)
    room = json.loads(room_file.read_text(encoding="utf-8"))
    room["entities"] = [{**copy.deepcopy(shared.player), **{k: e[k] for k in ("id", "x", "y") if k in e}}
                        if e.get("prefab_id") == "player" else e for e in room["entities"]]
    room_file.write_text(json.dumps(room), encoding="utf-8")
    project = Project(root, world_file)
    own = project.own_players()[start]["id"]
    assert not project.is_shared_player(own)
    project.edit_scene(lambda s: ops.set_dialogue_text(s, own, "Morning."))
    first = _add_line(project, own, "First.")
    project.edit_scene(lambda s: ops.remove_line(s, own, first))
    assert _add_line(project, own, "Second.") != first
    assert not any(i.startswith("player-line") for i in project.ids_seen)  # (not the shared player's scope)


# ---------------------------------------------------------------- a new river's id
@pytest.mark.parametrize("present, had, expected", [
    ([], [], "river"),
    (["river", "river-2", "river-3"], [], "river-4"),
    ([], ["river", "river-2"], "river-3"),
    (["river", "river-3"], ["river-2", "river-4"], "river-5"),
    (["river-2", "river-500"], ["river"], "river-3"),
    (["river", *(f"river-{n}" for n in range(2, 2001))], [], "river-2001"),
], ids=["none", "several", "had", "present and had", "high numbers", "a long run"])
def test_a_new_rivers_id_is_the_first_free_one_in_the_tools_order(present: list[str], had: list[str],
                                                                   expected: str) -> None:
    scene = {"settings": {"hd2d": {"rivers": [{"id": rid} for rid in present]}}}
    with ops.retired_ids({ops.scoped_id("river", "start", rid) for rid in had}), ops.in_room("start"):
        assert ops.unique_river_id(scene) == expected
    with ops.retired_ids({ops.scoped_id("river", "start", rid) for rid in had}), ops.in_room("cottage"):
        assert ops.unique_river_id(scene) == next(  # (another room's: what this room had doesn't count)
            r for r in ("river", *(f"river-{n}" for n in range(2, 3000))) if r not in present)
