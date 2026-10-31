"""F1 (#422): authoring from outside Studio writes a project's files only when no editor has it open.

``studio_session`` collapsed "no session" and "a session that couldn't be checked" into one answer, and ``apply``
took both as leave to write the files: with Mesh Studio open on unsaved work, a health request that timed out,
a half-written session record or a bridge that stopped answering let an AI's change go straight to disk. Now:
a verified session gets proposals, no session record at all allows the files, and anything in between refuses,
writes and creates nothing, and says why and what to do.

The sessions here are real (Studio's AI host on a loopback bridge, its documents holding unsaved edits); faults are
injected deterministically into the transport or the record, never by waiting.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib import error

import pytest

from engine import authoring, authoring_session
from engine.editor.live_session_bridge import session_file_path
from engine.mcp_server import live_session_client, tools
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.integration  # (F13-A, #422: bridges, exports, subprocesses; every default run has it)
REPO = Path(__file__).resolve().parents[1]
ROOM = "packs/core_regions/scenes/start.json"
ADD_SEXTON = [{"op": "place_prefab", "prefab": "person", "x": 320, "y": 224},
              {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"}]
ADD_CELLAR = [{"op": "add_room", "label": "Cellar"}]  # (a new room: new files, the world changed)
WARDEN = [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64},
          {"op": "rename_entity", "entity_id": "@0", "name": "Warden"}]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _files(root: Path) -> dict[str, str]:
    """Every file of the project and its hash: equal before and after means nothing was written or created."""
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class _Studio:
    """What StudioAIHost needs from Mesh Studio, without a window: the project as Studio holds it."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=ROOM))
        self.seen: list[str] = []

    def on_ai_proposal(self, proposal: Any) -> None:
        self.seen.append(proposal.title)

    def on_ai_decided(self, proposal: Any) -> None:
        self.seen.append(proposal.status)


@pytest.fixture
def studio(root: Path) -> Iterator[tuple[_Studio, StudioAIHost]]:
    """Mesh Studio with the project open and an unsaved edit (a Warden only it has), its live session running."""
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    studio = _Studio(Project(root, config["world_file"]))
    authoring.apply(studio.project, WARDEN)
    host = StudioAIHost(studio)
    host.start()
    stop = threading.Event()

    def pump() -> None:  # Studio's on_update, drained on its own thread here
        while not stop.is_set():
            host.drain()
            time.sleep(0.01)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    yield studio, host
    stop.set()
    thread.join(timeout=2)
    host.stop()


def _unsaved_work_intact(root: Path, studio: _Studio) -> None:
    assert studio.project.is_dirty and any(e.get("name") == "Warden" for e in studio.project.scene()["entities"])
    on_disk = json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]
    assert not any(e.get("name") in ("Warden", "Sexton") for e in on_disk)


def _every_entry_point(root: Path) -> dict[str, dict[str, Any]]:
    """What each way in says (the API, the MCP tools), each asked to change or read the project."""
    return {
        "apply": authoring_session.apply(root, ADD_SEXTON),
        "apply new room": authoring_session.apply(root, ADD_CELLAR),
        "apply dry run": authoring_session.apply(root, ADD_SEXTON, dry_run=True),
        "read": authoring_session.read_project(root),
        "propose": authoring_session.propose(root, ADD_SEXTON),
        "status": authoring_session.proposal_status(root, "p1"),
        "withdraw": authoring_session.withdraw(root, "p1"),
        "mcp apply_changes": tools.apply_changes(ADD_SEXTON, root=str(root)),
        "mcp read_project": tools.read_project(root=str(root)),
        "mcp propose_changes": tools.propose_changes(ADD_SEXTON, root=str(root)),
        "mcp apply_ops (authoring)": tools.apply_ops([{"type": "add_light", "scene_path": ROOM,
                                                       "light": {"x": 1, "y": 1}}], root=str(root)),
        "mcp apply_ops (files)": tools.apply_ops([{"type": "create_scene", "name": "cellar"}], root=str(root)),
        "mcp create_scene": tools.create_scene("cellar", root=str(root)),
    }


def _refused_everywhere(root: Path, problem: str) -> None:
    before = _files(root)
    answers = _every_entry_point(root)
    for name, answer in answers.items():
        found = answer.get("authoring", answer)  # (apply_ops through the authoring path wraps its outcome)
        assert answer["ok"] is False and found["reason"] == "studio_session_uncertain", (name, answer)
        assert found["problem"] == problem and found["discovery"] == str(session_file_path(root)), (name, found)
        assert "Nothing was changed" in found["message"] and str(session_file_path(root)) in found["message"]
    assert _files(root) == before, "nothing written, nothing created"


# --------------------------------------------------------------------- what each state allows

def test_with_no_session_record_the_files_are_changed_directly(root: Path) -> None:
    assert authoring_session.propose(root, ADD_SEXTON)["reason"] == "studio_not_open"
    assert authoring_session.read_project(root)["source"] == "files"
    done = authoring_session.apply(root, ADD_SEXTON)
    assert done["ok"] and done["source"] == "files" and done["written"] == [ROOM]
    assert any(e.get("name") == "Sexton" for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"])
    before = _files(root)
    assert authoring_session.apply(root, ADD_CELLAR)["ok"]  # (a new room makes new files: what refusals must not)
    assert set(_files(root)) - set(before)
    assert authoring_session.studio_state(root) == {"state": "none"}


def test_a_verified_studio_session_gets_proposals_and_its_unsaved_work_is_kept(root: Path, studio: Any) -> None:
    person, host = studio
    state = authoring_session.studio_state(root)
    assert state["state"] == "live" and state["host"] == "mesh_studio"
    before = _files(root)
    result = authoring_session.apply(root, ADD_SEXTON)
    assert result["ok"] and result["mode"] == "live_studio" and len(host.pending()) == 1
    read = authoring_session.read_project(root)
    assert read["source"] == "mesh_studio" and read["unsaved"] is True  # (what the person sees, unsaved included)
    assert tools.create_scene("cellar", root=str(root))["reason"] == "studio_open"  # (it wrote a file regardless)
    assert _files(root) == before
    _unsaved_work_intact(root, person)


# --------------------------------------------------------------------- a live Studio that can't be verified

def _health_fault(monkeypatch: pytest.MonkeyPatch, fault: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """The bridge's /health answer replaced by ``fault`` (which may raise); everything else as it is."""
    real = live_session_client._request_json

    def request(info: dict[str, Any], method: str, path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/health":
            return fault(real(info, method, path, *args, **kwargs))
        return real(info, method, path, *args, **kwargs)

    monkeypatch.setattr(live_session_client, "_request_json", request)


def _raise(exc: BaseException) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def fault(_health: dict[str, Any]) -> dict[str, Any]:
        raise exc
    return fault


@pytest.mark.parametrize(("fault", "problem"), [
    (_raise(TimeoutError("timed out")), "unverified_live_session"),
    (_raise(error.URLError(ConnectionRefusedError(10061, "refused"))), "unverified_live_session"),
    (_raise(json.JSONDecodeError("Expecting value", "<html>", 0)), "unverified_live_session"),
    (lambda health: {**health, "ok": False}, "unverified_live_session"),
    (lambda health: {**health, "session_id": "another"}, "session_mismatch"),
    (lambda health: {**health, "workspace_root": str(Path(health["workspace_root"]).parent)}, "workspace_mismatch"),
], ids=["timeout", "refused", "not json", "not ok", "another session", "another folder"])
def test_studio_with_unsaved_work_whose_health_check_fails_is_never_written_behind(
        root: Path, studio: Any, monkeypatch: pytest.MonkeyPatch,
        fault: Callable[[dict[str, Any]], dict[str, Any]], problem: str) -> None:
    person, host = studio
    _health_fault(monkeypatch, fault)
    _refused_everywhere(root, problem)
    assert authoring_session.studio_state(root)["state"] == "uncertain"
    assert host.pending() == [] and person.seen == []  # (and nothing half-sent to Studio)
    _unsaved_work_intact(root, person)


# --------------------------------------------------------------------- session records that can't be trusted

def _rewrite_record(root: Path, change: Callable[[dict[str, Any]], Any]) -> None:
    path = session_file_path(root)
    path.write_text(json.dumps(change(json.loads(path.read_text(encoding="utf-8")))), encoding="utf-8")


@pytest.mark.parametrize(("damage", "problem"), [
    (lambda root: session_file_path(root).write_text(session_file_path(root).read_text(encoding="utf-8")[:40],
                                                      encoding="utf-8"), "unreadable_live_session"),
    (lambda root: session_file_path(root).write_bytes(b"\xff\xfe not text"), "unreadable_live_session"),
    (lambda root: _rewrite_record(root, lambda info: [info]), "unreadable_live_session"),
    (lambda root: (session_file_path(root).unlink(), session_file_path(root).mkdir()), "unreadable_live_session"),
    (lambda root: _rewrite_record(root, lambda info: {**info, "schema_version": 99}), "invalid_live_session"),
    (lambda root: _rewrite_record(root, lambda info: {**info, "host": "0.0.0.0"}), "invalid_live_session"),
    (lambda root: _rewrite_record(root, lambda info: {k: v for k, v in info.items() if k != "token"}),
     "invalid_live_session"),
    (lambda root: _rewrite_record(root, lambda info: {**info, "token": "wrong"}), "unverified_live_session"),
    (lambda root: _rewrite_record(root, lambda info: {**info, "session_id": "another"}), "session_mismatch"),
], ids=["half written", "not utf-8", "not a record", "a folder", "unknown format", "not local", "incomplete",
        "wrong token", "another session"])
def test_a_session_record_that_cant_be_trusted_refuses_writes(root: Path, studio: Any,
                                                              damage: Callable[[Path], Any], problem: str) -> None:
    person, _host = studio
    damage(root)
    _refused_everywhere(root, problem)
    _unsaved_work_intact(root, person)


def test_a_record_copied_from_another_project_is_not_its_session(tmp_path: Path, root: Path, studio: Any) -> None:
    """A project copied with its .mesh folder while Studio had the original open: the record names the original,
    whose Studio answers. It is not the copy's session: changes neither go to the original nor to the copy's files."""
    person, host = studio
    copy = tmp_path / "copy"
    create_project(copy, "Game", template_id="blank")
    session_file_path(copy).parent.mkdir(parents=True, exist_ok=True)
    session_file_path(copy).write_bytes(session_file_path(root).read_bytes())
    _refused_everywhere(copy, "workspace_mismatch")
    state = authoring_session.studio_state(copy)
    assert state["state"] == "uncertain" and state["problem"]["reason"] == "workspace_mismatch"
    assert str(root.resolve()) in state["problem"]["why"]
    assert host.pending() == []
    assert tools.live_read_scene(root=str(copy))["reason"] == "workspace_mismatch"  # (the live tools agree)


# --------------------------------------------------------------------- a Studio that stopped answering

def test_a_studio_that_stopped_answering_is_not_taken_for_closed_and_recovers(root: Path, studio: Any) -> None:
    """Its bridge gone, its record left behind (frozen, or crashed): writes are refused, with what to do. Opening the
    project in Studio again replaces the record (proposals again); with Studio closed for sure, removing the record
    the message names lets the files be changed directly."""
    person, host = studio
    server = host.bridge._server
    assert server is not None
    server.shutdown()
    server.server_close()
    host.bridge._server = None
    _refused_everywhere(root, "unverified_live_session")
    message = authoring_session.apply(root, ADD_SEXTON)["message"]
    assert "didn't answer" in message and "open the project in Mesh Studio once" in message

    reopened = StudioAIHost(person)
    reopened.start()
    try:
        state = authoring_session.studio_state(root)
        assert state["state"] == "live" and state["info"]["session_id"] == reopened.bridge.session_id
    finally:
        reopened.stop()
    assert authoring_session.studio_state(root) == {"state": "none"}  # (closed properly: its record removed)
    assert authoring_session.apply(root, ADD_SEXTON)["source"] == "files"


# --------------------------------------------------------------------- no file writes after a live failure

def test_a_proposal_that_fails_is_never_written_to_the_files_instead(root: Path, studio: Any,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    person, host = studio
    real = authoring_session._request_json

    def request(info: dict[str, Any], method: str, path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if path == "/live/stage_proposal":
            raise error.URLError(ConnectionResetError(10054, "reset"))
        return real(info, method, path, *args, **kwargs)

    monkeypatch.setattr(authoring_session, "_request_json", request)
    before = _files(root)
    for answer in (authoring_session.apply(root, ADD_SEXTON), authoring_session.apply(root, ADD_CELLAR),
                   tools.apply_changes(ADD_SEXTON, root=str(root))):
        assert answer["ok"] is False and answer["reason"] == "studio_unreachable", answer
    assert _files(root) == before and host.pending() == []
    _unsaved_work_intact(root, person)


@pytest.mark.parametrize(("meanwhile", "reason"), [
    ({"state": "live", "host": "mesh_studio", "info": {}}, "studio_open"),
    ({"state": "live", "host": "legacy_editor", "info": {}}, "other_editor_open"),
    ({"state": "uncertain", "problem": {"reason": "unverified_live_session", "why": "it didn't answer",
                                        "discovery": "x"}}, "studio_session_uncertain"),
], ids=["studio", "another editor", "uncertain"])
def test_an_editor_opening_between_the_check_and_the_write_stops_the_write(root: Path, meanwhile: dict[str, Any],
                                                                           reason: str,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """apply checks again just before it writes (after working the changes out): Studio or another editor opened,
    or a record that can't be verified appeared, meanwhile: nothing written, a new room's files included."""
    states = iter([{"state": "none"}, meanwhile])
    monkeypatch.setattr(authoring_session, "studio_state", lambda _root, **_kw: next(states))
    before = _files(root)
    answer = authoring_session.apply(root, [*ADD_SEXTON, *ADD_CELLAR])
    assert answer["ok"] is False and answer["reason"] == reason
    assert _files(root) == before


# --------------------------------------------------------------------- another editor (not Mesh Studio)

@pytest.fixture
def legacy_editor(root: Path) -> Iterator[Any]:
    """The legacy editor with the project open on its own live session (a real, verified bridge), holding an object
    only it has (an unsaved edit, made through its live tools)."""
    from engine.editor.live_session_bridge import EditorLiveSessionBridge
    from tests.test_cocreative_live_ops import _make_controller

    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, root)
    bridge.start(write_discovery=True)
    added: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: added.update(tools.live_add_entity_from_prefab(
        "crate", 64, 80, name="unsaved_crate", root=str(root))))
    worker.start()
    while worker.is_alive():  # (the editor's own update loop, which applies live work)
        controller.drain_live_bridge()
        time.sleep(0.01)
    assert added["ok"] is True
    yield controller
    bridge.stop()


def _legacy_unsaved_work_intact(root: Path, controller: Any) -> None:
    held = controller.window.scene_controller._loaded_scene_data["entities"]
    assert [e.get("name") for e in held].count("unsaved_crate") == 1
    assert not any("unsaved_crate" in path.read_text(encoding="utf-8", errors="replace")
                   for path in root.rglob("*.json"))


def test_another_open_editor_is_never_written_behind_or_read_past(root: Path, legacy_editor: Any) -> None:
    """A verified session that isn't Mesh Studio's blocks every direct-file path, as Studio's does: create_scene and
    apply_ops wrote files under it (F1 review), and read_project offered the files as current although the editor
    held unsaved edits. Each now says another editor has it open, and what to do; nothing is written or created."""
    state = authoring_session.studio_state(root)
    assert state["state"] == "live" and state["host"] == "legacy_editor"
    before = _files(root)
    answers = _every_entry_point(root)
    for name in ("status", "withdraw"):  # (proposals are Mesh Studio's: none to ask about)
        assert answers.pop(name)["reason"] == "studio_not_open"
    said = {name: (answer["ok"], answer.get("authoring", answer).get("reason")) for name, answer in answers.items()}
    assert said == {name: (False, "other_editor_open") for name in answers}
    for name, answer in answers.items():
        found = answer.get("authoring", answer)
        assert found["host"] == "legacy_editor" and "Close it" in found["message"], (name, found)
    assert "source" not in answers["read"] and "rooms" not in answers["read"]  # (no disk copy passed off as current)
    assert _files(root) == before, "nothing written, nothing created"
    _legacy_unsaved_work_intact(root, legacy_editor)


def test_with_the_other_editor_closed_the_files_are_changed_again(root: Path, legacy_editor: Any) -> None:
    legacy_editor.live_bridge.stop()  # (closed properly: its record removed)
    assert authoring_session.studio_state(root) == {"state": "none"}
    assert tools.create_scene("cellar", root=str(root))["ok"] and (root / "cellar.json").is_file()
    assert authoring_session.read_project(root)["source"] == "files"


# --------------------------------------------------------------------- the CLI says so too

def test_mesh_author_refuses_and_says_why(root: Path, studio: Any, tmp_path: Path) -> None:
    person, _host = studio
    session_file_path(root).write_text("{", encoding="utf-8")  # (half-written)
    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"changes": ADD_SEXTON}), encoding="utf-8")
    before = _files(root)
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    for args in (["apply", str(changes)], ["read"], ["propose", str(changes)]):
        run = subprocess.run([sys.executable, "-m", "mesh_cli", "author", *args, "--project", str(root)], cwd=REPO,
                             capture_output=True, text=True, env=env, timeout=120)
        answer = json.loads(run.stdout)
        assert run.returncode == 1 and answer["reason"] == "studio_session_uncertain", (args, run.stdout, run.stderr)
        assert answer["problem"] == "unreadable_live_session" and "Nothing was changed" in answer["message"]
    assert _files(root) == before
    _unsaved_work_intact(root, person)
