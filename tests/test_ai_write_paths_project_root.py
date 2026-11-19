"""#462 R4 remediation: each writer holds the lock of the Mesh project its files are in, never a folder's own.

Independent review (Astra) of #521: the console's ``ai_job`` and ``mesh apply-plan`` locked the folder they started
in, so started inside a project (an ordinary folder of it) they took a lock nobody else uses and wrote behind the
Studio that had the project; ``ai_job`` could write into a nested project (its own owner) holding only the outer
project's lock; ``mesh undo-last-plan`` restored whatever its backup manifest named, and said "Undo successful"
when it restored nothing. Now every writer takes ``project_ownership.ownership_root`` (the project, wherever inside
it) and changes only ``in_project`` files; an undo checks every destination first and refuses whole.

The rule itself: tests/test_project_ownership_root.py. Every Studio / holder here is its own process (the OS lock).
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
from engine.editor import project_ownership
from engine.project_scaffold import create_project
from mesh_cli import ai as ai_cli
from tests.test_studio_project_ownership import REPO, StudioProcess

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)
REGION = "packs/core_regions"
ROOM = f"{REGION}/scenes/start.json"
LIGHT = {"x": 1, "y": 1, "radius": 9}
HOLD = ("import sys, time; sys.path.insert(0, sys.argv[1]); from engine.editor import project_ownership as o; "
        "h = o.acquire(sys.argv[2], sys.argv[3]); print('held', flush=True); time.sleep(120)")


@pytest.fixture
def outer(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    create_project(root / "inner", "Inner", template_id="blank")  # a nested Mesh project: its own owner
    return root


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    started: list[StudioProcess] = []

    def open_studio(root: Path) -> StudioProcess:
        studio = StudioProcess(root, log=tmp_path / f"studio_{len(started)}.log", env={"MESH_TEST_OWNER_WAIT": "0.3"})
        started.append(studio)
        assert studio.start["ready"], studio.start
        studio.ask("edit Unsaved Warden")
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


class _Holder:
    def __init__(self, root: Path, kind: str) -> None:
        self.proc = subprocess.Popen([sys.executable, "-c", HOLD, str(REPO), str(root), kind], stdout=subprocess.PIPE,
                                     text=True)
        assert self.proc.stdout is not None and self.proc.stdout.readline().strip() == "held"

    def end(self) -> None:
        self.proc.kill()
        self.proc.wait(timeout=30)
        assert self.proc.stdout is not None
        self.proc.stdout.close()


def _files(root: Path) -> dict[str, str]:
    skip = ("owner.lock", "live_session.json")
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name not in skip}


def _lights(path: Path) -> int:
    return len(json.loads(path.read_text(encoding="utf-8")).get("lights") or [])


def _ai_job(cwd: Path, job: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[str]:
    path = tmp_path / f"job_{len(list(tmp_path.glob('job_*.json')))}.json"
    path.write_text(json.dumps(job), encoding="utf-8")

    class Window:  # a game window, no editor
        def reload_scene(self) -> None:
            pass

    with monkeypatch.context() as patch:
        patch.chdir(cwd)
        console = ConsoleController(Window())
        console.execute_command(f"ai_job {path}")
    return console.lines[1:]


def _plan(tmp_path: Path, actions: list[dict[str, Any]], **inputs: Any) -> Path:
    path = tmp_path / f"plan_{len(list(tmp_path.glob('plan_*.json')))}.json"
    path.write_text(json.dumps({"wizard": "r4", "version": 1, "inputs": inputs, "actions": actions}), encoding="utf-8")
    return path


def _apply(plan: Path, cwd: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    with monkeypatch.context() as patch:
        patch.chdir(cwd)
        return ai_cli._handle_apply_plan(argparse.Namespace(command="apply-plan", plan_path=str(plan), from_triage=False,
                                                            no_lint=True, dry_run=False, run_tests=False, ai_safe=False))


def _undo(cwd: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    with monkeypatch.context() as patch:
        patch.chdir(cwd)
        return ai_cli._handle_undo_last_plan(argparse.Namespace())


NPC = {"type": "add_npc", "description": "AI adds a Ferryman", "args": {"scene_path": "scenes/start.json",
                                                                       "role": "villager", "name": "Ferryman"}}


# ------------------------------------------------------------- 1. Studio owns the project; started inside it
def test_started_from_a_folder_inside_a_project_studio_has_every_writer_is_refused(
        outer: Path, studios: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    studio = studios(outer)
    before = _files(outer)
    said = _ai_job(outer / REGION, {"operations": [{"type": "add_light", "scene_path": "scenes/start.json",
                                                    "light": LIGHT}]}, monkeypatch, tmp_path)
    assert said[0].startswith("[AI] ai_job: nothing was changed. Mesh Studio has this project open"), said
    assert _apply(_plan(tmp_path, [NPC]), outer / REGION, monkeypatch) == 1
    assert _undo(outer / REGION, monkeypatch) == 1
    out = capsys.readouterr().out
    assert "apply-plan: nothing was changed. Mesh Studio has this project open" in out
    assert "undo-last-plan: nothing was changed. Mesh Studio has this project open" in out
    assert _files(outer) == before and not (outer / REGION / ".mesh").exists()  # no lock of an inner folder's own
    assert studio.ask("save")["saved"] and not list(outer.rglob("*.outside-change*"))


# ------------------------------------------------------------- 2. Studio owns a nested project; the outer console
def test_the_outer_projects_console_cant_change_a_nested_project(outer: Path, studios: Any,
                                                                monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inner = outer / "inner"
    studios(inner)
    before = _files(outer)
    said = _ai_job(outer, {"operations": [{"type": "add_light", "scene_path": f"inner/{ROOM}", "light": LIGHT},
                                          {"type": "add_light", "scene_path": f"inner/{ROOM}", "light": LIGHT}]},
                   monkeypatch, tmp_path)
    assert said[0] == "[AI] Job failed (2 op(s)); see details:", said
    assert all("another Mesh project than the one held" in line for line in said[1:])
    assert _files(outer) == before  # the nested project's files (and the outer's) byte-identical
    # nor with Studio closed: the outer project's lock never covers the nested project
    held = project_ownership.owned(inner)
    assert held and held.get("kind") == project_ownership.STUDIO


# ------------------------------------------------------- 3 + 4. a historical undo manifest, now partly another project's
def test_an_undo_with_any_destination_in_another_project_is_refused_whole(outer: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # one plan (Studio closed): a room of this project changed, and a scene made in packs/region2
    assert _apply(_plan(tmp_path, [NPC]), outer / REGION, monkeypatch) == 0  # (from inside: the project's backup)
    assert _apply(_plan(tmp_path, [{"type": "create_scene", "description": "cellar", "args": {
        "path": "packs/region2/scenes/cellar.json", "template": "empty"}}], pack="region2"), outer, monkeypatch) == 0
    newest = sorted((outer / ".mesh/plan_backups").iterdir())[-1]
    manifest = json.loads((newest / "manifest.json").read_text(encoding="utf-8"))
    saved = newest / "files" / ROOM  # (as one plan touching both would have recorded it: valid entries beside it)
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes((outer / ROOM).read_bytes())
    manifest["modified"] = [ROOM]
    (newest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (outer / ROOM).write_text((outer / ROOM).read_text(encoding="utf-8").replace("{", '{"saved_since": 1, ', 1),
                              encoding="utf-8")
    region2 = outer / "packs/region2"  # later: region2 became a Mesh project of its own
    (region2 / "config.json").write_text(json.dumps({"title": "Region 2"}), encoding="utf-8")
    before = _files(outer)
    for owner in (None, project_ownership.STUDIO):  # nobody has it open, then Mesh Studio has it (another process)
        holder = _Holder(region2, owner) if owner else None
        try:
            assert _undo(outer, monkeypatch) == 1
        finally:
            if holder:
                holder.end()
        out = capsys.readouterr().out
        assert "[Mesh][Undo] Not restored: nothing was changed, because packs" in out and "in another project" in out
        assert "Undo successful" not in out and "Undo failed" in out
        assert _files(outer) == before  # neither the nested scene deleted nor the valid room restored


def test_an_undo_with_a_destination_outside_the_project_or_an_unsafe_alias_is_refused(
        outer: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert _apply(_plan(tmp_path, [NPC]), outer / REGION, monkeypatch) == 0
    newest = sorted((outer / REGION / ".mesh/plan_backups").iterdir())[-1]
    victim = tmp_path / "victim.json"
    victim.write_text("{}", encoding="utf-8")
    original = (newest / "manifest.json").read_text(encoding="utf-8")
    for bad in ({"created": [str(victim)]}, {"created": ["../../../victim.json"]}, {"modified": ["scenes/../../../../x.json"]},
                {"created": ["../../inner/config.json"]}, {"created": [7]}, {"modified": "scenes/start.json"},
                {"modified": ["scenes/start.json", "scenes/no_copy.json"]}):  # (a valid entry, one with no copy: none)
        # (entries are relative to where the plan ran: packs/core_regions)
        manifest = {**json.loads(original), **bad}
        (newest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        before = _files(outer)
        assert _undo(outer / REGION, monkeypatch) == 1, bad
        assert _files(outer) == before and victim.read_text(encoding="utf-8") == "{}"
    (newest / "manifest.json").write_text(original, encoding="utf-8")
    assert _undo(outer / REGION, monkeypatch) == 0  # the valid historical backup still restores
    assert "Ferryman" not in (outer / ROOM).read_text(encoding="utf-8")


def test_a_failed_undo_exits_nonzero_and_never_says_it_succeeded(outer: Path) -> None:
    (outer / ".mesh/plan_backups/1000_corrupt").mkdir(parents=True)  # a backup with no manifest
    for cwd in (outer, outer / REGION):
        ran = subprocess.run([sys.executable, "-m", "mesh_cli", "undo-last-plan"], cwd=cwd, capture_output=True,
                             text=True, timeout=300, env={**os.environ, "PYTHONPATH": str(REPO)})
        expected = "Corrupt backup (missing manifest)" if cwd == outer else "No backups found"
        assert ran.returncode == 1 and expected in ran.stdout and "Undo successful" not in ran.stdout, ran.stdout[-600:]


# --------------------------------------------- 5 + 6. ordinary folders and nested projects, each under its own lock
def test_inside_an_ordinary_folder_writers_work_under_the_projects_lock(outer: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path) -> None:
    started, go = threading.Event(), threading.Event()

    class Paused(AIOps):
        def apply_job(self, job_payload: dict[str, Any]) -> dict[str, Any]:
            started.set()
            assert go.wait(60)
            return super().apply_job(job_payload)

    monkeypatch.setattr(handlers_ai, "AIOps", Paused)
    said: list[str] = []
    job = threading.Thread(target=lambda: said.extend(_ai_job(outer / REGION, {"operations": [
        {"type": "add_light", "scene_path": "scenes/start.json", "light": LIGHT}]}, monkeypatch, tmp_path)))
    job.start()
    try:
        assert started.wait(60)
        assert (project_ownership.owned(outer, wait=0) or {}).get("kind") == project_ownership.AUTHORING  # the project's
        assert not (outer / REGION / ".mesh").exists()
    finally:
        go.set()
        job.join(60)
    assert said[0].startswith("[AI] Applied 1 operation(s)") and _lights(outer / ROOM) == 1
    assert _apply(_plan(tmp_path, [NPC]), outer / REGION, monkeypatch) == 0
    assert "Ferryman" in (outer / ROOM).read_text(encoding="utf-8")
    assert _undo(outer / REGION, monkeypatch) == 0 and "Ferryman" not in (outer / ROOM).read_text(encoding="utf-8")
    assert project_ownership.owned(outer) is None


def test_a_nested_project_is_edited_under_its_own_ownership(outer: Path, studios: Any, monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:
    inner = outer / "inner"
    studio = studios(outer)  # Mesh Studio has the outer project; the nested one is free
    before_outer = {k: v for k, v in _files(outer).items() if not k.startswith("inner/")}
    said = _ai_job(inner / REGION, {"operations": [{"type": "add_light", "scene_path": "scenes/start.json",
                                                    "light": LIGHT}]}, monkeypatch, tmp_path)
    assert said[0].startswith("[AI] Applied 1 operation(s)") and _lights(inner / ROOM) == 1
    assert _apply(_plan(tmp_path, [NPC]), inner / REGION, monkeypatch) == 0
    assert "Ferryman" in (inner / ROOM).read_text(encoding="utf-8")
    assert {k: v for k, v in _files(outer).items() if not k.startswith("inner/")} == before_outer
    assert project_ownership.owned(inner) is None and studio.ask("state")["unsaved"]


# --------------------------------------------- 8. two writers of one project from two folders: one lock, not two
def test_two_writers_starting_in_different_folders_cannot_both_hold_the_project(
        outer: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started, go = threading.Event(), threading.Event()

    class Paused(AIOps):
        def apply_job(self, job_payload: dict[str, Any]) -> dict[str, Any]:
            started.set()
            assert go.wait(60)
            return super().apply_job(job_payload)

    monkeypatch.setattr(handlers_ai, "AIOps", Paused)
    said: list[str] = []
    job = threading.Thread(target=lambda: said.extend(_ai_job(outer / REGION / "scenes", {"operations": [
        {"type": "add_light", "scene_path": "start.json", "light": LIGHT}]}, monkeypatch, tmp_path)))
    job.start()
    try:
        assert started.wait(60)
        before = _files(outer)
        plan = _plan(tmp_path, [{**NPC, "args": {**NPC["args"], "scene_path": ROOM}}], pack="core_regions")
        second = subprocess.run([sys.executable, "-m", "mesh_cli", "apply-plan", "--no-lint", str(plan)], cwd=outer,
                                capture_output=True, text=True, timeout=300, env={**os.environ, "PYTHONPATH": str(REPO)})
        assert second.returncode == 1 and "Another tool is writing this project's files" in second.stdout, second.stdout[-600:]
        assert _files(outer) == before
    finally:
        go.set()
        job.join(60)
    assert said[0].startswith("[AI] Applied 1 operation(s)") and project_ownership.owned(outer) is None
