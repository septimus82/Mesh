"""The authoring API from outside Studio: offline files, the apply_ops adapter, the CLI, and the
live proposal round trip through a real loopback bridge to a Studio host."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import authoring, authoring_session
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from engine.studio_ai import StudioAIHost
from engine.studio_project import Project

pytestmark = pytest.mark.fast
REPO = Path(__file__).resolve().parents[1]
ADD_SEXTON = [{"op": "place_prefab", "prefab": "person", "x": 320, "y": 224},
              {"op": "rename_entity", "entity_id": "@0", "name": "Sexton"}]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _room(root: Path) -> dict:
    return json.loads((root / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))


def test_offline_apply_writes_valid_files_or_nothing(root: Path) -> None:
    preview = authoring_session.apply(root, ADD_SEXTON, dry_run=True)
    assert preview["ok"] and any("adds 'Sexton'" in line for line in preview["summary"])
    assert not any(e.get("name") == "Sexton" for e in _room(root)["entities"])
    done = authoring_session.apply(root, ADD_SEXTON)
    assert done["ok"] and done["written"] == ["packs/core_regions/scenes/start.json"]
    assert any(e.get("name") == "Sexton" for e in _room(root)["entities"])
    before = _room(root)
    refused = authoring_session.apply(root, [*ADD_SEXTON, {"op": "set_look", "entity_id": "@0", "scale": 0}])
    assert not refused["ok"] and refused["index"] == 2 and "size" in refused["message"]
    assert _room(root) == before


def test_apply_ops_on_a_studio_project_goes_through_the_same_validated_path(root: Path) -> None:
    result = tools.apply_ops([{"type": "add_entity_from_prefab", "scene_path": "packs/core_regions/scenes/start.json",
                               "prefab_name": "person", "x": 96, "y": 96}], root=str(root))
    assert result["ok"] and result["mode"] == "files" and result["results"][0]["type"] == "add_entity_from_prefab"
    placed = [e for e in _room(root)["entities"] if e.get("name") == "Person"]
    assert len(placed) == 1 and placed[0]["x"] == 96.0


def test_the_cli_and_the_api_produce_the_same_room(root: Path, tmp_path: Path) -> None:
    other = tmp_path / "copy"
    create_project(other, "Game", template_id="blank")
    changes = tmp_path / "changes.json"
    changes.write_text(json.dumps({"changes": ADD_SEXTON}), encoding="utf-8")
    run = subprocess.run([sys.executable, "-m", "mesh_cli", "author", "apply", str(changes), "--project", str(other)],
                         cwd=REPO, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(REPO)})
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["ok"]
    authoring_session.apply(root, ADD_SEXTON)
    assert _room(root) == _room(other)


class _FakeStudio:
    """What StudioAIHost needs from Mesh Studio, without a window."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.window = SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path="packs/core_regions/scenes/start.json"))
        self.seen: list[str] = []

    def on_ai_proposal(self, proposal) -> None:
        self.seen.append(proposal.title)

    def on_ai_decided(self, proposal) -> None:
        self.seen.append(proposal.status)


@pytest.fixture
def live(root: Path):
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    studio = _FakeStudio(Project(root, config["world_file"]))
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


def test_while_studio_is_open_changes_are_proposed_never_written(root: Path, live) -> None:
    studio, host = live
    before = _room(root)
    result = authoring_session.apply(root, ADD_SEXTON)  # an AI calling apply: it becomes a proposal
    assert result["ok"] and result["mode"] == "live_studio" and "proposed there" in result["note"]
    assert _room(root) == before and studio.seen == ["Changes from an AI"]
    status = authoring_session.proposal_status(root, result["proposal_id"])
    assert status["proposal"]["status"] == "pending" and any("Sexton" in s for s in status["proposal"]["summary"])
    refused = authoring_session.propose(root, [{"op": "move_entity", "entity_id": "Nobody", "x": 1, "y": 1}])
    assert not refused["ok"] and "no object 'Nobody'" in refused["message"]  # invalid: refused at once
    assert tools.live_accept_proposal(result["proposal_id"], root=str(root))["reason"] == "needs_person"
    assert authoring_session.withdraw(root, result["proposal_id"])["ok"]
    assert host.proposals[0].status == "rejected" and _room(root) == before


def test_a_persons_edit_and_an_ai_proposal_both_survive_unless_they_touch_the_same_thing(root: Path, live) -> None:
    studio, host = live
    project = studio.project
    seen = authoring_session.read_project(root)
    assert seen["source"] == "mesh_studio" and seen["revision"] == 0
    # The person paints while the AI prepares an NPC: both survive.
    project.edit_scene(lambda s: __import__("engine.project_ops", fromlist=["x"]).paint_tiles(s, "walls", [(2, 2)], 9))
    staged = authoring_session.propose(root, ADD_SEXTON, title="Add the sexton", base_revision=seen["revision"])
    proposal = host.proposals[-1]
    assert host.accept(proposal)["ok"]
    room = project.scene()
    assert any(e.get("name") == "Sexton" for e in room["entities"])
    walls = next(layer for layer in room["tilemap"]["tile_layers"] if layer["id"] == "walls")["tiles"]
    assert 9 in walls
    assert project.undo() and not any(e.get("name") == "Sexton" for e in project.scene()["entities"])
    assert 9 in next(layer for layer in project.scene()["tilemap"]["tile_layers"] if layer["id"] == "walls")["tiles"]
    assert project.redo()
    assert staged["proposal"]["title"] == "Add the sexton"
    # The same property both ways: a conflict, reported, nothing lost.
    seen = authoring_session.read_project(root)
    authoring_session.propose(root, [{"op": "rename_entity", "entity_id": "Sexton", "name": "Gravedigger"}],
                              base_revision=seen["revision"])
    project.edit_scene(lambda s: authoring.ops.rename_entity(s, proposal.created[0], "Warden"))
    clash = host.accept(host.proposals[-1])
    assert clash["reason"] == "conflict" and clash["conflicts"][0]["studio"] == "Warden"
    assert clash["conflicts"][0]["ai"] == "Gravedigger"
    assert any(e.get("name") == "Warden" for e in project.scene()["entities"])


def test_the_old_one_call_add_tool_never_reports_a_success_that_didnt_happen(root: Path, live) -> None:
    _studio, host = live
    result = tools.live_add_entity_from_prefab("person", 100, 100, root=str(root))
    assert result["ok"] is False and "no operation 'add_entity_from_prefab'" in result["message"]
    assert host.pending() == []


def test_a_studio_save_keeps_a_version_something_else_wrote_meanwhile(root: Path) -> None:
    import os

    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    authoring.apply(project, ADD_SEXTON)
    scene_file = root / "packs/core_regions/scenes/start.json"
    outside = scene_file.read_text(encoding="utf-8").replace('"Player"', '"Changed outside"')
    scene_file.write_text(outside, encoding="utf-8")
    os.utime(scene_file, (time.time() + 5, time.time() + 5))  # a later write, whatever the clock's resolution
    project.save()
    assert project.last_save_backups == ["packs/core_regions/scenes/start.json.outside-change.bak"]
    assert (root / project.last_save_backups[0]).read_text(encoding="utf-8") == outside
    assert any(e.get("name") == "Sexton" for e in _room(root)["entities"])


def test_apply_ops_wont_write_files_under_an_open_studio(root: Path, live) -> None:
    _studio, host = live
    before = _room(root)
    refused = tools.apply_ops([{"type": "create_scene", "name": "cellar"}], root=str(root))
    assert refused["ok"] is False and refused["reason"] == "studio_open" and _room(root) == before
    # Lights go the shared authoring path (Milestone 13): proposed to the open Studio, the files untouched.
    proposed = tools.apply_ops([{"type": "add_light", "scene_path": "packs/core_regions/scenes/start.json",
                                 "light": {"x": 1, "y": 1}}], root=str(root))
    assert proposed["ok"] is True and _room(root) == before and len(host.pending()) == 1
