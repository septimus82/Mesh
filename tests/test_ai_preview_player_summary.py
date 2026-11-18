"""An AI's proposal about the shared player says what it changes (#519 follow-up).

The game has one player: rooms hold only where it starts, and what it is and says is the project's ``player`` document
(``Project.player``). ``authoring.summarize`` went through rooms only, so a proposal changing the player's conversation
(or its picture, its behaviours) reached the person as "(no visible change)": they approved a change the preview
didn't show. The summary now reads the player document too, in the words an object's changes already get.

Each Studio test runs a real StudioAIHost on its loopback bridge; the AI goes through ``authoring_session`` with R1's
``base_revision_id``; the person edits through ``Project.edit_scene``; acceptance is ``StudioAIHost.accept``.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import authoring, authoring_session
from engine import project_ops as ops
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project
from tests.test_studio_object_identity import (
    _add_line,
    _add_player_line,
    _everywhere,
    _npc,
    _player,
    _remove_player_line,
    _Studio,
    _talking_player,
)

pytestmark = pytest.mark.integration  # (F13-A, #422: bridges; every default run has it)
NOTHING = ["(no visible change)"]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="hd2d_rpg")
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
    read = authoring_session.read_project(root)
    staged = authoring_session.propose(root, changes, title="An AI's change", base_revision_id=read["revision_id"])
    assert staged["ok"], staged
    proposal = next(p for p in host.proposals if p.proposal_id == staged["proposal"]["proposal_id"])
    assert staged["proposal"]["summary"] == proposal.summary  # (the tool is told what the person is shown)
    return proposal


def _about_player(summary: list[str]) -> list[str]:
    return [line for line in summary if line.startswith("The player (every room): ")]


# ---------------------------------------------------------------- what the person is shown
def test_a_change_to_the_players_line_is_shown_not_no_visible_change(root: Path, studio: Any) -> None:
    """The misleading preview, reproduced: the AI gives the player's line a speaker."""
    person, host = studio
    project = person.project
    start, _other = _talking_player(project)
    line = _add_player_line(project, start, "The bridge is out.")
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": _player(project), "node_id": line,
                                   "speaker": "Ghost"}])
    assert ghost.summary != NOTHING, "a change to the player's conversation was previewed as no visible change"
    assert ghost.summary == [f"The player (every room): conversation line '{line}' speaker: (none) -> 'Ghost'"]


def test_each_kind_of_change_to_the_players_conversation_is_named(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    start, other = _talking_player(project)
    line = _add_player_line(project, start, "The bridge is out.")
    player = _player(project)
    said = _propose(root, host, [{"op": "set_line", "entity_id": player, "node_id": line, "text": "Mind the bridge."}])
    assert said.summary == [
        f"The player (every room): conversation line '{line}' says: 'The bridge is out.' -> 'Mind the bridge.'"]

    added = _propose(root, host, [{"op": "add_line", "entity_id": _player(project, other), "text": "Hm.",
                                   "room": other}])  # (made in another room: the same player)
    assert any("conversation line 'line_3': (none) -> " in line_ and "Hm." in line_ for line_ in _about_player(
        added.summary)), added.summary
    assert len(_about_player(added.summary)) == len(added.summary)  # nothing about a room: no room changed

    removed = _propose(root, host, [{"op": "remove_line", "entity_id": player, "node_id": line}])
    assert any(f"conversation line '{line}': " in line_ and line_.endswith(" -> (none)")
               for line_ in _about_player(removed.summary)), removed.summary

    settings = _propose(root, host, [{"op": "set_conversation", "entity_id": player, "speaker": "Hero", "once": True,
                                      "require_flags": ["met_guard"]}])
    assert set(_about_player(settings.summary)) == {
        "The player (every room): conversation speaker: 'Player' -> 'Hero'",
        "The player (every room): conversation only once: (none) -> true",
        "The player (every room): can be talked to when these flags are set: (none) -> [\"met_guard\"]",
    } == set(settings.summary), settings.summary

    renamed = _propose(root, host, [{"op": "rename_entity", "entity_id": player, "name": "Wanderer"}])
    assert renamed.summary == ["The player (every room): conversation speaker: 'Player' -> 'Wanderer'",
                               "The player (every room): name: 'Player' -> 'Wanderer'"]  # (not only what it says)


def test_a_proposal_about_the_player_and_others_lists_both_and_the_others_as_before(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    npc = _npc(project)
    start, _other = _talking_player(project)
    line = _add_player_line(project, start, "The bridge is out.")
    npc_line = _add_line(project, npc, "Evening.")
    npc_change = {"op": "set_line", "entity_id": npc, "node_id": npc_line, "speaker": "Ghost"}
    crate = {"op": "set_structure", "structure_id": "crate_1", "rotation": 90}
    alone = _propose(root, host, [npc_change, crate])
    assert alone.summary and not _about_player(alone.summary)
    mixed = _propose(root, host, [npc_change, {"op": "set_line", "entity_id": _player(project), "node_id": line,
                                               "speaker": "Ghost"}, crate])
    assert [line_ for line_ in mixed.summary if line_ not in _about_player(mixed.summary)] == alone.summary
    assert _about_player(mixed.summary) == [
        f"The player (every room): conversation line '{line}' speaker: (none) -> 'Ghost'"]


def test_a_proposal_that_changes_nothing_still_says_so(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    start, _other = _talking_player(project)
    line = _add_player_line(project, start, "The bridge is out.")
    same = _propose(root, host, [{"op": "set_line", "entity_id": _player(project), "node_id": line,
                                  "text": "The bridge is out."}])
    assert same.summary == NOTHING


# ---------------------------------------------------------------- previewing changes nothing; accepting as before
def test_previewing_is_read_only_and_accepting_undoing_and_redoing_work_as_before(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    start, _other = _talking_player(project)
    line = _add_player_line(project, start, "The bridge is out.")
    documents, seen = copy.deepcopy(project.all_documents()), set(project.ids_seen)
    revision, undo = authoring_session.read_project(root)["revision_id"], project.can_undo()
    change = [{"op": "set_line", "entity_id": _player(project), "node_id": line, "speaker": "Ghost"},
              {"op": "add_line", "entity_id": _player(project), "text": "Hm."}]
    dry = authoring.summarize(*authoring.dry_run(project, change))
    ghost = _propose(root, host, change)
    assert ghost.summary == dry and len(_about_player(dry)) >= 2
    assert project.all_documents() == documents and project.ids_seen == seen and project.can_undo() == undo
    assert authoring_session.read_project(root)["revision_id"] == revision and not project.can_redo()

    accepted = host.accept(ghost)
    assert accepted["ok"], accepted
    made = accepted["created"][1]
    assert all(lines[line]["speaker"] == "Ghost" and lines[made]["text"] == "Hm." for lines in _everywhere(project))
    assert any(f"conversation line '{made}'" in line_ for line_ in ghost.summary)  # the preview named the id made
    assert project.undo() and project.all_documents() == documents  # one step back: all of it
    assert project.redo() and all(lines[line]["speaker"] == "Ghost" for lines in _everywhere(project))


def test_a_stale_proposal_about_the_player_still_conflicts_and_keeps_its_preview(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    start, other = _talking_player(project)
    line = _add_player_line(project, start, "The bridge is out.")
    ghost = _propose(root, host, [{"op": "set_line", "entity_id": _player(project), "node_id": line,
                                   "speaker": "Ghost"}])
    shown = list(ghost.summary)
    project.edit_scene(lambda s: ops.set_line(s, _player(project, other), line, speaker="Hero"), other)  # the person's
    clash = host.accept(ghost)
    assert clash["ok"] is False and clash["reason"] == "conflict" and ghost.summary == shown
    assert all(lines[line]["speaker"] == "Hero" for lines in _everywhere(project))

    gone = _propose(root, host, [{"op": "set_line", "entity_id": _player(project), "node_id": line, "text": "Boo."}])
    _remove_player_line(project, start, line)  # (#462 R3: the line deleted and another written)
    replacement = _add_player_line(project, start, "The ferry runs at dawn.")
    refused = host.accept(gone)
    assert replacement != line and refused["ok"] is False and refused["reason"] == "conflict"
    assert all(lines[replacement]["text"] == "The ferry runs at dawn." for lines in _everywhere(project))


def test_a_revision_of_another_session_is_still_refused_before_any_preview(root: Path, studio: Any) -> None:
    person, host = studio
    project = person.project
    _talking_player(project)
    read = authoring_session.read_project(root)
    session = project.session
    other = ("e" if session[0] == "f" else "f") + session[1:] + read["revision_id"][len(session):]
    refused = authoring_session.propose(root, [{"op": "set_dialogue_text", "entity_id": _player(project),
                                                "text": "Boo."}], base_revision_id=other)
    assert refused["reason"] == "revision_from_another_session" and host.proposals == [] and person.inbox == []


# ---------------------------------------------------------------- the summary itself
PLAYER = {"name": "Player", "sprite": "hero.png", "behaviours": ["PlayerController", "Dialogue"],
          "behaviour_config": {"Dialogue": {"once": False, "dialogue": {"speaker": "Player", "start": "root", "nodes": {
              "root": {"text": "Morning.", "next": "line_2"}, "line_2": {"text": "The bridge is out."}}}}}}
ROOMS = {"start": {"entities": [{"id": "p", "prefab_id": "player", "x": 1, "y": 2},
                                {"id": "g", "name": "Guard", "x": 5, "y": 5}]}}


def _docs(player: Any = PLAYER, rooms: Any = ROOMS) -> dict[str, Any]:
    return {"world": {"scenes": {"start": {"label": "Start"}}}, "rooms": copy.deepcopy(rooms),
            "player": copy.deepcopy(player)}


def _with(path: list[str], value: Any) -> dict[str, Any]:
    player = copy.deepcopy(PLAYER)
    at: Any = player
    for key in path[:-1]:
        at = at[key]
    if value is None:
        del at[path[-1]]
    else:
        at[path[-1]] = value
    return _docs(player)


def test_the_summary_reads_the_player_document() -> None:
    nodes = ["behaviour_config", "Dialogue", "dialogue", "nodes"]
    assert authoring.summarize(_docs(), _docs()) == []
    assert authoring.summarize(_docs(), _with([*nodes, "line_2", "text"], "Mind the bridge.")) == [
        "The player (every room): conversation line 'line_2' says: 'The bridge is out.' -> 'Mind the bridge.'"]
    assert authoring.summarize(_docs(), _with([*nodes, "line_3"], {"text": "Hm."})) == [
        "The player (every room): conversation line 'line_3': (none) -> {\"text\": \"Hm.\"}"]
    assert authoring.summarize(_docs(), _with([*nodes, "line_2"], None)) == [
        "The player (every room): conversation line 'line_2': {\"text\": \"The bridge is out.\"} -> (none)"]
    assert authoring.summarize(_docs(), _with(["sprite"], "heroine.png")) == [
        "The player (every room): picture: 'hero.png' -> 'heroine.png'"]
    assert authoring.summarize(_docs(), _with(["behaviour_config", "Dialogue", "once"], True)) == [
        "The player (every room): conversation only once: false -> true"]


def test_the_summary_of_everything_else_is_as_it_was() -> None:
    moved = copy.deepcopy(ROOMS)
    moved["start"]["entities"][0]["x"], moved["start"]["entities"][1]["name"] = 9, "Captain"
    room_lines = ["Start: 'p' x: 1 -> 9", "Start: 'Captain' name: 'Guard' -> 'Captain'"]
    assert authoring.summarize(_docs(), _docs(rooms=moved)) == room_lines  # (where a room's player starts: the room's)
    for missing in ({"rooms": ROOMS}, {"rooms": ROOMS, "player": None}):  # views without a player (older callers,
        after = {**missing, "rooms": moved}  # projects whose rooms have their own)
        assert authoring.summarize(missing, after) == [line.replace("Start:", "start:") for line in room_lines]
    assert authoring.summarize({"rooms": ROOMS, "player": None}, _docs()) == []  # (no operation makes the player
    assert authoring.summarize(_docs(), {"rooms": ROOMS, "player": None}) == []  # shared, or stops it being)
    both = _with(["name"], "Wanderer")
    both["rooms"] = moved
    assert authoring.summarize(_docs(), both) == [*room_lines, "The player (every room): name: 'Player' -> 'Wanderer'"]
