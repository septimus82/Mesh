"""#462 R4 remediation B (independent verification of remediation A): undo preflight on types; identity captured.

Finding 2: ``mesh undo-last-plan`` checked where each manifest entry pointed, not what is there now. A created file
whose path is now a folder failed only after the first created file had been deleted; a modified file whose path is
now a folder got its copy put *inside* the folder, and the undo said "Undo successful". Now every entry is checked
first (a file or nothing where a file is restored or deleted, no file where a folder is needed, the copy a file in the
backup) and one bad entry refuses the whole undo, nothing changed, exit 1.

Finding 3: a writer holding a nested project's lock kept writing its files after the nested ``config.json`` was
removed (they were the outer project's then). The lock now covers what it was taken as (``Ownership.owns``); the
console's ``ai_job`` and ``apply-plan`` stop. Studio and lock holders are their own processes (the OS lock).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import engine.console_runtime.handlers_ai as handlers_ai
from engine.ai_ops import AIOps
from engine.console_controller import ConsoleController
from engine.project_scaffold import create_project
from engine.tooling.plan_executor import PlanExecutor
from mesh_cli import ai as ai_cli
from tests.test_studio_project_ownership import REPO, StudioProcess

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)
ROOM = "packs/core_regions/scenes/start.json"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    started: list[StudioProcess] = []

    def open_studio(project: Path) -> StudioProcess:
        studio = StudioProcess(project, log=tmp_path / f"studio_{len(started)}.log", env={"MESH_TEST_OWNER_WAIT": "0.3"})
        started.append(studio)
        assert studio.start["ready"], studio.start
        studio.ask("edit Unsaved Warden")
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _files(path: Path) -> dict[str, str]:
    skip = ("owner.lock", "live_session.json")
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file() and p.name not in skip}


def _backup(root: Path, manifest: dict[str, Any], copies: dict[str, str] | None = None) -> Path:
    backup = root / ".mesh/plan_backups/2000_manual"
    (backup / "files").mkdir(parents=True)
    for rel, text in (copies or {}).items():
        (backup / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
        (backup / "files" / rel).write_text(text, encoding="utf-8")
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return backup


def _undo_cli(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "mesh_cli", "undo-last-plan"], cwd=root, capture_output=True, text=True,
                          timeout=300, env={**os.environ, "PYTHONPATH": str(REPO)})


# ------------------------------------------------------------------------------------------------------ finding 2
def test_a_created_file_that_is_now_a_folder_refuses_the_undo_before_anything_is_deleted(root: Path) -> None:
    (root / "scenes").mkdir()
    (root / "scenes/made.json").write_text("{}", encoding="utf-8")
    (root / "scenes/became_a_folder.json").mkdir()
    (root / "scenes/became_a_folder.json/inside.txt").write_text("keep", encoding="utf-8")
    _backup(root, {"created": ["scenes/made.json", "scenes/became_a_folder.json"], "modified": []})
    before = _files(root)
    ran = _undo_cli(root)
    assert ran.returncode == 1 and "Undo successful" not in ran.stdout, ran.stdout[-800:]
    assert "Not restored: nothing was changed, because scenes/became_a_folder.json is a folder" in ran.stdout
    assert _files(root) == before  # the first created file is still there


def test_a_modified_file_that_is_now_a_folder_is_never_copied_into_it(root: Path) -> None:
    (root / "scenes/room.json").mkdir(parents=True)
    _backup(root, {"created": [], "modified": ["scenes/room.json"]}, {"scenes/room.json": '{"restored": true}'})
    before = _files(root)
    ran = _undo_cli(root)
    assert ran.returncode == 1 and "Undo successful" not in ran.stdout, ran.stdout[-800:]
    assert "scenes/room.json is a folder" in ran.stdout
    assert _files(root) == before and not (root / "scenes/room.json/room.json").exists()


@pytest.mark.parametrize("bad", ["folder_above_is_a_file", "copy_is_a_folder", "copy_missing"])
def test_one_bad_entry_among_valid_ones_refuses_the_whole_undo(root: Path, bad: str) -> None:
    saved_room = (root / ROOM).read_text(encoding="utf-8")
    (root / ROOM).write_text(saved_room.replace("{", '{"saved_since": 1, ', 1), encoding="utf-8")
    (root / "made.json").write_text("{}", encoding="utf-8")
    copies = {ROOM: saved_room}
    manifest: dict[str, Any] = {"created": ["made.json"], "modified": [ROOM]}
    if bad == "folder_above_is_a_file":
        (root / "notes.txt").write_text("a file where a folder is needed", encoding="utf-8")
        copies["notes.txt/x.json"] = "{}"
        manifest["modified"].append("notes.txt/x.json")
    elif bad == "copy_is_a_folder":
        manifest["modified"].append("scenes/other.json")
    else:
        manifest["modified"].append("scenes/never_copied.json")
    backup = _backup(root, manifest, copies)
    if bad == "copy_is_a_folder":
        (backup / "files/scenes/other.json").mkdir(parents=True)
    before = _files(root)
    ran = _undo_cli(root)
    assert ran.returncode == 1 and "Not restored: nothing was changed" in ran.stdout, ran.stdout[-800:]
    assert _files(root) == before  # neither the valid room restored nor made.json deleted


def test_missing_destinations_and_valid_backups_still_restore(root: Path) -> None:
    saved_room = (root / ROOM).read_text(encoding="utf-8")
    (root / ROOM).unlink()  # a modified file gone since: put back
    _backup(root, {"created": ["gone_already.json"], "modified": [ROOM]}, {ROOM: saved_room})
    ran = _undo_cli(root)
    assert ran.returncode == 0 and "Undo successful" in ran.stdout, ran.stdout[-800:]
    assert (root / ROOM).read_text(encoding="utf-8") == saved_room


# ------------------------------------------------------------------------------------------------------ finding 3
def _marker_removed_mid_write(root: Path, studios: Any, monkeypatch: pytest.MonkeyPatch, work: Any,
                              pause: tuple[Any, str]) -> tuple[Any, dict[str, str], dict[str, str]]:
    inner = root / "inner"
    studio = studios(root)  # Mesh Studio has the outer project
    started, go = threading.Event(), threading.Event()
    owner_cls, name = pause
    original = getattr(owner_cls, name)

    def paused(self: Any, *args: Any, **kwargs: Any) -> Any:
        started.set()
        assert go.wait(60)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(owner_cls, name, paused)
    result: list[Any] = []
    thread = threading.Thread(target=lambda: result.append(work(inner)))
    thread.start()
    try:
        assert started.wait(60)  # the writer holds the nested project's lock, mid-write
        (inner / "config.json").unlink()  # the nested project stops being one: its files are the outer project's
        before = _files(root)
    finally:
        go.set()
        thread.join(60)
    assert studio.ask("state")["unsaved"]
    return result[0], before, _files(root)


def test_the_console_stops_once_its_project_stopped_being_one(root: Path, studios: Any, monkeypatch: pytest.MonkeyPatch,
                                                              tmp_path: Path) -> None:
    create_project(root / "inner", "Inner", template_id="blank")
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"operations": [{"type": "add_light", "scene_path": ROOM,
                                               "light": {"x": 1, "y": 1, "radius": 9}}]}), encoding="utf-8")

    class Window:
        def reload_scene(self) -> None:
            pass

    def work(inner: Path) -> list[str]:
        with monkeypatch.context() as patch:
            patch.chdir(inner)
            console = ConsoleController(Window())
            console.execute_command(f"ai_job {job}")
        return console.lines[1:]

    said, before, after = _marker_removed_mid_write(root, studios, monkeypatch, work, (handlers_ai.AIOps, "apply_job"))
    assert said[0] == "[AI] Job failed (1 op(s)); see details:" and "another Mesh project than the one held" in said[1]
    assert after == before


def test_a_plan_stops_once_its_project_stopped_being_one(root: Path, studios: Any, monkeypatch: pytest.MonkeyPatch,
                                                         tmp_path: Path) -> None:
    create_project(root / "inner", "Inner", template_id="blank")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"wizard": "r4b", "version": 1, "inputs": {"pack": "core_regions"}, "actions": [
        {"type": "add_npc", "description": "AI adds a Ferryman",
         "args": {"scene_path": ROOM, "role": "villager", "name": "Ferryman"}}]}), encoding="utf-8")

    def work(inner: Path) -> int:
        with monkeypatch.context() as patch:
            patch.chdir(inner)
            return ai_cli._handle_apply_plan(argparse.Namespace(
                command="apply-plan", plan_path=str(plan), from_triage=False, no_lint=True, dry_run=False,
                run_tests=False, ai_safe=False))

    code, before, after = _marker_removed_mid_write(root, studios, monkeypatch, work, (PlanExecutor, "_run_action"))
    assert code == 1 and after == before
    assert "Ferryman" not in (root / "inner" / ROOM).read_text(encoding="utf-8")


def test_aiops_with_no_owner_is_unchanged(root: Path) -> None:
    # (callers that hold no lock, the existing tests' sandboxes: as before remediation B)
    assert AIOps(root).add_light(ROOM, {"x": 1, "y": 1, "radius": 9}).ok
