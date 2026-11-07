"""F10 (#422): a decided AI proposal lets go of its whole-project copies; a waiting one keeps them.

A proposal waiting for the person holds what the tool read (``base``) and its result (``after``), to compare with
the person's edits when it is accepted. Checked:
- once accepted, rejected or failed, both copies and the changes are let go, and what Studio and the tool see stays
  (id, status, summary, message, conflicts, created ids), for status queries and Studio's history alike;
- a proposal in conflict keeps them and can still be accepted once the clash is gone;
- the waiting-proposal limit refuses more, with nothing staged;
- decided history is bounded, and the bridge forgets with Studio;
- no whole-project document stays reachable from decided proposals;
- undo still takes an accepted proposal back;
- nothing is written to the files;
- a revision snapshot the proposal was based on (F6) is left intact.

The long-session measurement is tooling/f10_proposal_memory.py.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine import authoring, authoring_session, studio_ai
from engine.project_scaffold import create_project
from engine.studio_ai import PENDING_MAX, StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (project files, and loopback bridges for the MCP path)
WORLD = "packs/core_regions/worlds/main.json"


class _Studio:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=project.path(project.current)))
        self.decided: list[str] = []

    def on_ai_proposal(self, proposal: Any) -> None: ...

    def on_ai_decided(self, proposal: Any) -> None:
        self.decided.append(proposal.status)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    create_project(tmp_path / "game", "Game", template_id="starter")
    return tmp_path / "game"


@pytest.fixture
def host(root: Path) -> StudioAIHost:
    project = Project.open(root, WORLD)
    assert project is not None
    return StudioAIHost(_Studio(project))


@pytest.fixture
def live(host: StudioAIHost) -> Iterator[StudioAIHost]:
    """``host`` with its live session, its queue drained on another thread (Studio's on_update)."""
    host.start()
    stop = threading.Event()

    def pump() -> None:
        while not stop.is_set():
            host.drain()
            time.sleep(0.002)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    yield host
    stop.set()
    thread.join(timeout=2)
    host.stop()


def _place(x: float) -> list[dict[str, Any]]:
    return [{"op": "place_prefab", "prefab": "person", "x": x, "y": 300}]


def _stage(host: StudioAIHost, changes: list[dict[str, Any]], **payload: Any) -> studio_ai.Proposal:
    staged = host.stage_proposal_payload({"changes": changes, **payload})
    assert isinstance(staged, studio_ai.Proposal), staged
    staged.proposal_id = f"p{len(host.proposals)}"
    return staged


def _guide(host: StudioAIHost) -> str:
    return next(e["id"] for e in host.project.scene()["entities"] if e.get("name") == "Guide")


def _holds_a_project(obj: Any) -> bool:
    """Whether a whole-project document (a dict with "world" and "rooms") is reachable from ``obj``."""
    seen: set[int] = set()
    stack = [obj]
    while stack:
        item = stack.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, dict):
            if "world" in item and "rooms" in item:
                return True
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, studio_ai.Proposal):
            stack.append(vars(item))
    return False


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and ".mesh" not in p.relative_to(root).parts}


# --------------------------------------------------------------------- decided: copies let go, the record kept

def test_accepted_rejected_and_failed_proposals_let_go_of_their_copies(host: StudioAIHost, root: Path) -> None:
    files = _files(root)
    accepted, rejected = _stage(host, _place(100), title="Add one"), _stage(host, _place(200), title="Add two")
    guide = _guide(host)
    failing = _stage(host, [{"op": "remove_entity", "entity_id": guide}], title="Remove the Guide")
    for proposal in (accepted, rejected, failing):  # (waiting: both copies kept)
        assert _holds_a_project(proposal.base) and _holds_a_project(proposal.after) and proposal.changes
    assert host.accept(accepted)["ok"] is True
    host.reject_proposal(rejected)
    authoring.apply(host.project, [{"op": "remove_entity", "entity_id": guide}])  # (the person removed it first)
    outcome = host.accept(failing)
    assert failing.status in ("failed", "conflict"), outcome
    if failing.status == "conflict":  # (a clash is still waiting; rejecting decides it)
        host.reject_proposal(failing)
    for proposal, status in ((accepted, "accepted"), (rejected, "rejected"), (failing, failing.status)):
        assert proposal.status == status
        assert (proposal.base, proposal.after, proposal.changes) == ({}, {}, []), status
        assert not _holds_a_project(proposal)
        view = host.proposal_status(proposal.proposal_id)["proposal"]  # (what the tool sees)
        assert view == proposal.view() and view["title"] and view["summary"] and view["message"]
    assert accepted.created and host.proposal_status(accepted.proposal_id)["proposal"]["created"]
    assert [p.view() for p in host.proposals] == [accepted.view(), rejected.view(), failing.view()]  # (history)
    assert host.accept(rejected) == {"ok": False, "reason": "rejected"}  # (decided stays decided)
    assert _files(root) == files  # (nothing written: the files change only when the person saves)


def test_a_proposal_in_conflict_keeps_its_copies_and_still_works(host: StudioAIHost) -> None:
    guide = _guide(host)
    clash = _stage(host, [{"op": "rename_entity", "entity_id": guide, "name": "Elder"}])
    separate = _stage(host, _place(400))
    authoring.apply(host.project, [{"op": "rename_entity", "entity_id": guide, "name": "Mentor"}])  # (the person)
    result = host.accept(clash)
    assert result["reason"] == "conflict" and clash.status == "conflict" and clash.conflicts
    assert _holds_a_project(clash.base) and _holds_a_project(clash.after) and clash.changes  # (still waiting)
    assert host.accept(separate)["ok"] is True  # (a separate edit: both survive, as before)
    assert any(e.get("name") == "Mentor" for e in host.project.scene()["entities"])
    host.project.undo()  # (the person takes their part back: no clash any more)
    host.project.undo()
    assert host.accept(clash)["ok"] is True and clash.status == "accepted"
    assert any(e.get("name") == "Elder" for e in host.project.scene()["entities"])
    assert (clash.base, clash.after, clash.changes) == ({}, {}, []) and clash.conflicts  # (its record kept)


def test_undo_still_takes_an_accepted_proposal_back(host: StudioAIHost) -> None:
    before = len(host.project.scene()["entities"])
    proposal = _stage(host, _place(500))
    host.accept(proposal)
    made = list(proposal.created.values())
    assert len(host.project.scene()["entities"]) == before + 1 and proposal.base == {}
    assert host.project.undo() and len(host.project.scene()["entities"]) == before
    assert host.project.redo() and any(e["id"] in made for e in host.project.scene()["entities"])


def test_a_revision_snapshot_the_proposal_was_based_on_is_left_intact(host: StudioAIHost) -> None:
    host.read_live_scene()  # (the tool reads: Studio keeps this revision's documents, F6)
    revision = host.project.revision
    authoring.apply(host.project, _place(600))  # (the person edits since)
    kept = copy.deepcopy(host._snapshots[revision])
    proposal = _stage(host, _place(700), base_revision=revision)
    assert proposal.base == kept  # (checked against what the tool read)
    host.reject_proposal(proposal)
    assert proposal.base == {} and host._snapshots[revision] == kept  # (let go of, never emptied)


# --------------------------------------------------------------------- limits

def test_too_many_waiting_proposals_are_refused_with_nothing_staged(live: StudioAIHost, root: Path) -> None:
    for i in range(PENDING_MAX):
        assert authoring_session.propose(root, _place(10 + i))["ok"]
    refused = authoring_session.propose(root, _place(999))
    assert refused["ok"] is False and refused["reason"] == "too_many_pending"
    assert refused["pending"] == refused["limit"] == PENDING_MAX and "withdraw" in refused["message"]
    assert len(live.proposals) == PENDING_MAX and len(live.pending()) == PENDING_MAX  # (nothing staged)
    assert authoring_session.withdraw(root, live.bridge.list_pending_proposals()[0]["proposal_id"])["ok"]
    assert authoring_session.propose(root, _place(999))["ok"]  # (a decided one frees a place)


def test_decided_history_is_bounded_and_the_bridge_forgets_too(live: StudioAIHost, root: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(studio_ai, "HISTORY_KEPT", 3)
    ids = []
    for i in range(5):  # (the person decides in Studio: the bridge still has each, until Studio forgets it)
        staged = authoring_session.propose(root, _place(20 + i))
        ids.append(staged["proposal_id"])
        live.reject_proposal(next(p for p in live.proposals if p.proposal_id == staged["proposal_id"]))
    waiting = authoring_session.propose(root, _place(99))["proposal_id"]
    assert [p.proposal_id for p in live.proposals] == [*ids[2:], waiting]  # (the last 3 decided, and the waiting one)
    assert set(live.bridge._proposals) == {*ids[2:], waiting}
    withdrawn = authoring_session.propose(root, _place(98))["proposal_id"]
    assert authoring_session.withdraw(root, withdrawn)["status"] == "rejected"
    assert withdrawn not in live.bridge._proposals  # (withdrawn by the tool: the bridge let go of it at once)
    gone = authoring_session.proposal_status(root, ids[0])
    assert gone["ok"] is False and gone["reason"] == "proposal_not_found" and "last 3" in gone["message"]
    assert authoring_session.proposal_status(root, ids[4])["proposal"]["status"] == "rejected"
    assert not any(_holds_a_project(p) for p in live.proposals if p.status != "pending")
    assert not any(_holds_a_project(p) for p in live.bridge._proposals.values() if p.status != "pending")


def test_status_queries_over_mcp_tell_the_truth_after_release(live: StudioAIHost, root: Path) -> None:
    staged = authoring_session.propose(root, _place(30), title="Add a person")
    proposal = next(p for p in live.proposals if p.proposal_id == staged["proposal_id"])
    live.accept(proposal)  # (the person, in Studio: the bridge still has it, already let go of)
    status = authoring_session.proposal_status(root, staged["proposal_id"])["proposal"]
    assert status["status"] == "accepted" and status["title"] == "Add a person" and status["created"]
    assert json.dumps(status) and not _holds_a_project(live.bridge._proposals[staged["proposal_id"]])
    assert authoring_session.withdraw(root, staged["proposal_id"])["status"] == "accepted"  # (decided stays)
