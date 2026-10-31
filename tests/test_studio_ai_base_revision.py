"""F6 (#422): an AI proposal based on a revision Mesh Studio no longer keeps is refused, never rebased.

Studio checks a proposal against the project as the AI read it (``base_revision``), so that when the person accepts
it, changes they made since are compared with the AI's: separate edits both survive, the same property changed both
ways is a conflict. Studio keeps the last ``SNAPSHOTS_KEPT`` revisions it was read at. A ``base_revision`` it had
dropped was silently replaced by the current revision, so the AI's change no longer met the person's as a conflict:
accepting it overwrote what the person had done. Inputs that aren't revisions (``True``, ``-1``, a future revision,
``"7"``) were rebased the same way, or coerced into another revision.

Each test runs a real StudioAIHost on its loopback bridge, the AI going through ``authoring_session`` (what the MCP
tools and ``mesh author`` call), and the person editing Studio's own documents.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import authoring, authoring_session
from engine.mcp_server import tools
from engine.mcp_server.live_session_client import _load_verified_session, _request_json
from engine.project_scaffold import create_project
from engine.studio_ai import SNAPSHOTS_KEPT, StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.fast
REPO = Path(__file__).resolve().parents[1]
ROOM = "packs/core_regions/scenes/start.json"


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window: the project as Studio holds it."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM))
        self.inbox: list[str] = []  # what the person is shown to review

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
    """Mesh Studio with the project open, a Warden in its start room (unsaved), its live session running."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    person = _Studio(Project(root, config["world_file"]))
    authoring.apply(person.project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64},
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


def _rename(project: Project, entity_id: str, name: str) -> None:
    project.edit_scene(lambda room: authoring.ops.rename_entity(room, entity_id, name))


def _paint(project: Project, col: int) -> None:
    project.edit_scene(lambda room: authoring.ops.paint_tiles(room, "walls", [(col, 1)], 9))


def _names(project: Project) -> list[str]:
    return [str(e.get("name")) for e in project.scene()["entities"]]


def _evict(root: Path, project: Project, reads: int = SNAPSHOTS_KEPT) -> None:
    """The person keeps working and the project is read again ``reads`` times (other tools, an AI polling)."""
    for i in range(reads):
        _paint(project, 1 + i % 5)
        assert authoring_session.read_project(root)["ok"]


def _guard(warden: str) -> list[dict[str, Any]]:
    return [{"op": "rename_entity", "entity_id": warden, "name": "Guard"}]


def _nothing_staged(person: _Studio, host: StudioAIHost, documents: dict[str, Any], revision: int,
                    root: Path, files: dict[str, bytes]) -> None:
    assert host.proposals == [] and host.pending() == [] and person.inbox == []
    assert person.project.revision == revision and person.project.all_documents() == documents
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()} == files


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------- the person's work is protected

def test_a_proposal_on_an_evicted_revision_is_refused_not_rebased_over_the_persons_work(root: Path, studio: Any) -> None:
    """The AI reads (a Warden), the person renames it Keeper and keeps working; the AI's revision drops out of what
    Studio keeps. Its rename to Guard used to be checked against today's project and accepted over the Keeper with
    no conflict. Now it's refused: nothing staged or changed, the current revision and a fresh read asked for."""
    person, host, warden = studio
    read = authoring_session.read_project(root)
    _rename(person.project, warden, "Keeper")
    _evict(root, person.project)
    documents, revision, files = copy.deepcopy(person.project.all_documents()), person.project.revision, _files(root)

    refused = authoring_session.propose(root, _guard(warden), base_revision=read["revision"])

    assert refused["ok"] is False and refused["reason"] == "base_revision_unavailable", refused
    assert refused["base_revision"] == read["revision"] and refused["revision"] == revision
    assert f"revision {revision}" in refused["message"] and "Read the project again" in refused["message"]
    _nothing_staged(person, host, documents, revision, root, files)
    assert "Keeper" in _names(person.project)
    # Read again: the AI now sees the Keeper, and its proposal is checked against what the person has.
    fresh = authoring_session.read_project(root)
    assert fresh["revision"] == revision
    staged = authoring_session.propose(root, _guard(warden), base_revision=fresh["revision"])
    assert staged["ok"] and staged["proposal"]["base_revision"] == revision
    assert any("Keeper" in line and "Guard" in line for line in staged["proposal"]["summary"]), staged["proposal"]


def test_eviction_follows_the_snapshots_studio_keeps(root: Path, studio: Any) -> None:
    """One read fewer than SNAPSHOTS_KEPT later, the AI's revision is still kept, and the overlapping rename meets
    the person's as a conflict at acceptance; with SNAPSHOTS_KEPT later reads it is gone, and refused."""
    person, host, warden = studio
    kept = authoring_session.read_project(root)["revision"]
    _rename(person.project, warden, "Keeper")
    _evict(root, person.project, reads=SNAPSHOTS_KEPT - 1)
    staged = authoring_session.propose(root, _guard(warden), base_revision=kept)
    assert staged["ok"] and staged["proposal"]["base_revision"] == kept
    clash = host.accept(host.proposals[-1])
    assert clash["reason"] == "conflict" and clash["conflicts"][0]["studio"] == "Keeper"
    assert clash["conflicts"][0]["ai"] == "Guard" and "Keeper" in _names(person.project)
    authoring_session.withdraw(root, staged["proposal_id"])
    _evict(root, person.project, reads=1)
    assert authoring_session.propose(root, _guard(warden), base_revision=kept)["reason"] == "base_revision_unavailable"


# --------------------------------------------------------------------- what still works as before

def test_an_older_revision_studio_keeps_is_still_compared_with_the_persons_changes(root: Path, studio: Any) -> None:
    person, host, warden = studio
    read = authoring_session.read_project(root)["revision"]
    _paint(person.project, 3)  # the person paints: separate from the AI's change
    _rename(person.project, warden, "Keeper")  # and renames: the same property as the AI's
    independent = authoring_session.propose(root, [{"op": "place_prefab", "prefab": "person", "x": 320, "y": 224},
                                                   {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"}],
                                            base_revision=read)
    overlapping = authoring_session.propose(root, _guard(warden), base_revision=read)
    assert independent["proposal"]["base_revision"] == read == overlapping["proposal"]["base_revision"]
    first, second = host.proposals
    assert host.accept(first)["ok"]  # both survive: the person's paint and Keeper, the AI's Sexton
    walls = next(layer for layer in person.project.scene()["tilemap"]["tile_layers"] if layer["id"] == "walls")
    assert 9 in walls["tiles"] and {"Keeper", "Sexton"} <= set(_names(person.project))
    clash = host.accept(second)  # the same name changed both ways: a conflict, the person's Keeper stands
    assert clash["reason"] == "conflict" and "Keeper" in _names(person.project) and "Guard" not in _names(person.project)


def test_the_current_revision_works_without_a_read_at_it(root: Path, studio: Any) -> None:
    """The current revision needs no kept snapshot: the project as it is now is its documents."""
    person, host, warden = studio
    _rename(person.project, warden, "Keeper")  # (no read since: Studio keeps nothing at this revision)
    current = person.project.revision
    assert current not in host._snapshots
    staged = authoring_session.propose(root, _guard(warden), base_revision=current)
    assert staged["ok"] and staged["proposal"]["base_revision"] == current
    assert host.accept(host.proposals[-1])["ok"] and "Guard" in _names(person.project)


def test_without_a_base_revision_it_is_proposed_against_the_project_as_it_is_now(root: Path, studio: Any) -> None:
    person, host, warden = studio
    authoring_session.read_project(root)
    _rename(person.project, warden, "Keeper")
    _evict(root, person.project)
    staged = authoring_session.propose(root, _guard(warden))
    assert staged["ok"] and staged["proposal"]["base_revision"] == person.project.revision
    assert tools.live_stage_proposal([{"op": "rename_entity", "entity_id": warden, "name": "Watch"}],
                                     root=str(root))["ok"]  # (the older tool: no base_revision, as before)


# --------------------------------------------------------------------- inputs that aren't revisions

@pytest.mark.parametrize("given", [True, False, -1, "future", "3", 2.0, [1], {"revision": 1}],
                         ids=["true", "false", "negative", "future", "a string", "a float", "a list", "an object"])
def test_something_that_isnt_a_revision_is_refused_not_replaced(root: Path, studio: Any, given: Any) -> None:
    person, host, warden = studio
    for _ in range(3):  # (revisions 1.. are kept, so a coerced True, "3" or 2.0 would find one)
        _paint(person.project, 2)
        authoring_session.read_project(root)
    current = person.project.revision
    given = current + 1 if given == "future" else given
    documents, files = copy.deepcopy(person.project.all_documents()), _files(root)
    refused = authoring_session.propose(root, _guard(warden), base_revision=given)
    assert refused["ok"] is False and refused["reason"] == "invalid_base_revision", refused
    assert refused["base_revision"] == given and refused["revision"] == current
    assert f"0 to {current}" in refused["message"]
    _nothing_staged(person, host, documents, current, root, files)


# --------------------------------------------------------------------- every way in says the same

def test_the_bridge_mcp_and_cli_all_refuse_the_evicted_revision_the_same_way(root: Path, studio: Any,
                                                                            tmp_path: Path) -> None:
    person, host, warden = studio
    old = authoring_session.read_project(root)["revision"]
    _rename(person.project, warden, "Keeper")
    _evict(root, person.project)
    current = person.project.revision
    info, _failure = _load_verified_session(root)
    assert info is not None
    bridge = _request_json(info, "POST", "/live/stage_proposal", {"changes": _guard(warden), "base_revision": old},
                           timeout=6.0)
    mcp = tools.propose_changes(_guard(warden), base_revision=old, root=str(root))
    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"changes": _guard(warden)}), encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "mesh_cli", "author", "propose", str(changes), "--project", str(root),
                          "--base-revision", str(old)], cwd=REPO, capture_output=True, text=True, timeout=120,
                         env={**os.environ, "PYTHONPATH": str(REPO)})
    cli = json.loads(run.stdout)
    assert run.returncode == 1, run.stdout + run.stderr
    for answer in (bridge, mcp, cli):
        assert (answer["ok"], answer["reason"], answer["base_revision"], answer["revision"]) == (
            False, "base_revision_unavailable", old, current), answer
        assert "Read the project again" in answer["message"]
    assert host.proposals == [] and person.inbox == [] and "Keeper" in _names(person.project)
