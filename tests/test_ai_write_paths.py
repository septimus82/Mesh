"""#462 R4: the AI commands that write a project's files directly own it first, like every outside writer (R2).

Reproduced before the fix: with Mesh Studio open on a project, unsaved work in it,

- ``mesh apply-plan`` wrote the room behind Studio (exit 0); Studio's next save then dropped the AI's change without
  a word (only an ``.outside-change.bak`` kept it), and ``mesh undo-last-plan`` put the files back to before the plan,
  deleting the person's *saved* work from disk;
- the console's ``ai_job`` (reachable in Studio's play-test: ` opens the console) wrote the room and the quest file
  behind Studio; Studio's next save dropped the room's change but the quest stayed: half a job.

Now ``apply-plan`` (not ``--dry-run``) and ``undo-last-plan`` own the project for the whole command, and ``ai_job``
is refused inside an editing window and owns the project elsewhere. Each Studio here is its own process
(``tests/studio_owner_process.py``); the commands are the production ones, the CLI in a subprocess where it matters.
The real-window console check is tests/test_ai_write_paths_gpu.py.
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
from types import SimpleNamespace
from typing import Any

import pytest

import engine.console_runtime.handlers_ai as handlers_ai
from engine.ai_ops import AIOps
from engine.console_controller import ConsoleController
from engine.editor import project_ownership
from engine.project_scaffold import create_project
from engine.tooling.plan_executor import PlanExecutor
from mesh_cli import ai as ai_cli
from tests.test_studio_project_ownership import REPO, ROOM, StudioProcess

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)
PLAN = {"wizard": "r4", "version": 1, "inputs": {"pack": "core_regions"},
        "actions": [{"type": "add_npc", "description": "AI adds a Ferryman",
                     "args": {"scene_path": ROOM, "role": "villager", "name": "Ferryman", "x": 96, "y": 96}}]}
JOB = {"operations": [{"type": "add_light", "scene_path": ROOM, "light": {"x": 200, "y": 120, "radius": 90}},
                      {"type": "add_quest_definition", "quest_id": "ai_quest", "quest": {"title": "From the AI"}}]}
STUDIO_OPEN = "Mesh Studio has this project open, and its unsaved work isn't in the files"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    (path / "assets/data").mkdir(parents=True, exist_ok=True)
    (path / "assets/data/quests.json").write_text('{"quests": []}\n', encoding="utf-8")
    (tmp_path / "plan.json").write_text(json.dumps(PLAN), encoding="utf-8")
    (tmp_path / "job.json").write_text(json.dumps(JOB), encoding="utf-8")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    started: list[StudioProcess] = []

    def open_studio(root: Path, *args: str) -> StudioProcess:
        studio = StudioProcess(root, *args, log=tmp_path / f"studio_{len(started)}.log",
                               env={"MESH_TEST_OWNER_WAIT": "0.3"})
        started.append(studio)
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _files(root: Path) -> dict[str, str]:
    """Every file of the project and its hash, the ownership note and session record aside (``.mesh``'s plan backups
    and history count: they are the command's writes too)."""
    skip = {".mesh/owner.lock", ".mesh/live_session.json"}
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.relative_to(root).as_posix() not in skip}


def _names(root: Path) -> list[str]:
    return [str(e.get("name")) for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]]


def _mesh(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "mesh_cli", *args], cwd=root, capture_output=True, text=True,
                          timeout=300, env={**os.environ, "PYTHONPATH": str(REPO)})


def _apply_args(plan: Path, **extra: Any) -> argparse.Namespace:
    return argparse.Namespace(**{"command": "apply-plan", "plan_path": str(plan), "from_triage": False,
                                 "no_lint": False, "dry_run": False, "run_tests": False, "ai_safe": False, **extra})


class _Window:
    """A game window as the console sees it; ``studio`` / ``project_ownership`` / ``editor_controller`` as given."""

    def __init__(self, **parts: Any) -> None:
        self.reloads = 0
        self.__dict__.update(parts)

    def reload_scene(self) -> None:
        self.reloads += 1


def _ai_job(window: Any, job: Path) -> list[str]:
    console = ConsoleController(window)
    console.execute_command(f"ai_job {job}")
    return console.lines[1:]  # (after the command itself)


# ------------------------------------------------------------------- mesh apply-plan / undo-last-plan, Studio open
def test_apply_plan_and_undo_are_refused_while_mesh_studio_has_the_project(root: Path, studios: Any) -> None:
    studio = studios(root)
    assert studio.start["ready"]
    studio.ask("edit Unsaved Warden")  # the person's unsaved work
    before = _files(root)

    applied = _mesh(root, "apply-plan", str(root.parent / "plan.json"))
    assert applied.returncode == 1, applied.stdout[-1500:]
    assert f"apply-plan: nothing was changed. {STUDIO_OPEN}" in applied.stdout
    assert "Executing plan" not in applied.stdout
    assert _files(root) == before  # nothing written: no room, no backup, no history

    preview = _mesh(root, "apply-plan", "--dry-run", str(root.parent / "plan.json"))  # read-only: still works
    assert preview.returncode == 0 and "applied successfully" in preview.stdout, preview.stdout[-1500:]
    assert _files(root) == before

    held = studio.ask("state")
    assert held["names"] == ["Player", "Unsaved Warden"] and held["unsaved"]
    assert studio.ask("save")["saved"] == [ROOM]  # the person's save: their work, nothing lost, no outside change
    assert _names(root) == ["None", "Unsaved Warden"] and not list(root.rglob("*.outside-change*"))
    assert studio.close() == 0

    # a plan applied with Studio closed, then Studio open with more unsaved work: undoing it is refused too
    assert _mesh(root, "apply-plan", str(root.parent / "plan.json")).returncode == 0
    assert _names(root) == ["None", "Unsaved Warden", "Ferryman"]
    again = studios(root)
    assert again.start["ready"]
    again.ask("edit Second Warden")
    saved = _files(root)
    undone = _mesh(root, "undo-last-plan")
    assert undone.returncode == 1 and f"undo-last-plan: nothing was changed. {STUDIO_OPEN}" in undone.stdout
    assert _files(root) == saved
    assert again.ask("state")["names"] == ["Player", "Unsaved Warden", "Ferryman", "Second Warden"]
    assert again.close() == 0
    assert _mesh(root, "undo-last-plan").returncode == 0  # closed: the undo is the person's to run
    assert _names(root) == ["None", "Unsaved Warden"]


def test_apply_plan_with_studio_closed_writes_and_lets_the_project_go(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    assert ai_cli._handle_apply_plan(_apply_args(root.parent / "plan.json")) == 0
    assert _names(root) == ["None", "Ferryman"]
    assert list((root / ".mesh/plan_backups").glob("*/manifest.json")) and list((root / ".mesh/plan_history").glob("*.json"))
    assert project_ownership.owned(root) is None
    assert ai_cli._handle_undo_last_plan(argparse.Namespace()) == 0
    assert _names(root) == ["None"] and project_ownership.owned(root) is None


def test_a_competing_writer_or_an_editor_holding_the_project_stops_the_plan(root: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(root)
    before = _files(root)
    for kind, said in ((project_ownership.AUTHORING, "Another tool is writing this project's files right now"),
                       (project_ownership.EDITOR, "Another Mesh editor has this project open")):
        holder = subprocess.Popen([sys.executable, "-c", (
            "import sys,time; sys.path.insert(0, sys.argv[1]); from engine.editor import project_ownership as o; "
            "h = o.acquire(sys.argv[2], sys.argv[3]); print('held', flush=True); time.sleep(60)"),
            str(REPO), str(root), kind], stdout=subprocess.PIPE, text=True)
        try:
            assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
            assert ai_cli._handle_apply_plan(_apply_args(root.parent / "plan.json")) == 1
            assert said in capsys.readouterr().out
            assert ai_cli._handle_undo_last_plan(argparse.Namespace()) == 1
            assert _files(root) == before
        finally:
            holder.kill()
            holder.wait(timeout=30)
            assert holder.stdout is not None
            holder.stdout.close()


def test_mesh_studio_opening_during_a_plan_is_turned_away_until_it_is_written(root: Path, studios: Any,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    started, go = threading.Event(), threading.Event()
    run_action = PlanExecutor._run_action

    def paused(self: PlanExecutor, action: Any) -> None:
        started.set()
        assert go.wait(60)
        run_action(self, action)

    monkeypatch.setattr(PlanExecutor, "_run_action", paused)
    result: list[int] = []
    writer = threading.Thread(target=lambda: result.append(ai_cli._handle_apply_plan(_apply_args(root.parent / "plan.json"))))
    writer.start()
    try:
        assert started.wait(60)  # the plan is between reading the project and writing it
        refused = studios(root)
        assert refused.start["ready"] is False and "An outside tool is writing this project's files" in refused.start["refused"]
    finally:
        go.set()
        writer.join(60)
    assert result == [0] and _names(root) == ["None", "Ferryman"] and project_ownership.owned(root) is None
    opened = studios(root)  # written and let go: Studio opens it, the plan's change in it
    assert opened.start["ready"] and "Ferryman" in opened.ask("state")["names"]
    assert opened.close() == 0


def test_studio_and_a_plan_starting_at_once_never_both_have_the_project(root: Path, tmp_path: Path) -> None:
    """Started at the same instant, three times: whichever owns the project first, Studio never holds a view the
    plan then writes behind. Either the plan was refused (nothing written) or Studio read the room after it."""
    applied = 0
    for attempt in range(3):
        gate, opening = tmp_path / f"gate_{attempt}", []
        starting = threading.Thread(target=lambda: opening.append(StudioProcess(  # (it answers once through the gate)
            root, log=tmp_path / f"race_{attempt}.log", env={"MESH_TEST_OWNER_WAIT": "2.0",
                                                            "MESH_TEST_START_GATE": str(gate)})))
        starting.start()
        writer = subprocess.Popen([sys.executable, "-c", (
            "import sys, time, argparse, pathlib; sys.path.insert(0, sys.argv[1]); from mesh_cli import ai; "
            "from engine.editor import project_ownership; gate = pathlib.Path(sys.argv[3]); print('ready', flush=True)\n"
            "while not gate.exists(): time.sleep(0.005)\n"
            "print('exit', ai._handle_apply_plan(argparse.Namespace(command='apply-plan', plan_path=sys.argv[2], "
            "from_triage=False, no_lint=False, dry_run=False, run_tests=False, ai_safe=False)), flush=True)"),
            str(REPO), str(root.parent / "plan.json"), str(gate)], cwd=root, stdout=subprocess.PIPE, text=True)
        try:
            assert writer.stdout is not None and writer.stdout.readline().strip() == "ready"
            before = _files(root)
            gate.write_text("go", encoding="utf-8")
            starting.join(120)
            studio = opening[0]
            assert studio.start["ready"], studio.start  # (it waits up to 2 s, as Studio does: a plan is quicker)
            code = int(next(line for line in writer.stdout if line.startswith("exit")).split()[1])
            names = studio.ask("state")["names"]
            print(f"attempt {attempt}: {'plan first, Studio waited' if code == 0 else 'Studio first, plan refused'}")
            if code == 0:  # the plan had the project first: Studio waited, then read the plan's change
                applied += 1
            else:  # Studio had it first: the plan wrote nothing
                assert _files(root) == before
            assert names.count("Ferryman") == applied == _names(root).count("Ferryman"), (code, names)
            assert studio.close() == 0
        finally:
            writer.kill()
            writer.wait(timeout=30)
            assert writer.stdout is not None
            writer.stdout.close()
            gate.write_text("go", encoding="utf-8")  # (never left waiting)
            starting.join(120)
            for left in opening:
                if left.proc.poll() is None:
                    left.proc.kill()
                    left.end()


def test_a_writer_killed_mid_plan_leaves_the_project_free(root: Path, studios: Any) -> None:
    script = ("import sys, time; sys.path.insert(0, sys.argv[1]); from engine.tooling.plan_executor import PlanExecutor; "
              "PlanExecutor._run_action = lambda self, action: (print('writing', flush=True), time.sleep(60)); "
              "from mesh_cli import ai; import argparse; "
              "ai._handle_apply_plan(argparse.Namespace(command='apply-plan', plan_path=sys.argv[2], from_triage=False, "
              "no_lint=False, dry_run=False, run_tests=False, ai_safe=False))")
    writer = subprocess.Popen([sys.executable, "-c", script, str(REPO), str(root.parent / "plan.json")], cwd=root,
                              stdout=subprocess.PIPE, text=True)
    try:
        assert writer.stdout is not None
        assert any(line.strip() == "writing" for line in writer.stdout)  # (it owns the project now)
        assert project_ownership.owned(root, wait=0)["kind"] == project_ownership.AUTHORING
    finally:
        writer.kill()  # a crash: none of its own code runs
        writer.wait(timeout=30)
        assert writer.stdout is not None
        writer.stdout.close()
    assert project_ownership.owned(root) is None
    studio = studios(root)
    assert studio.start["ready"] and studio.close() == 0


def test_failed_plans_and_unavailable_ownership_leave_no_hold_and_no_change(root: Path, monkeypatch: pytest.MonkeyPatch,
                                                                         capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(root)
    broken = root.parent / "broken.json"  # an action that fails part way: the project is let go all the same
    broken.write_text(json.dumps({**PLAN, "actions": [{**PLAN["actions"][0], "args": {
        **PLAN["actions"][0]["args"], "scene_path": "packs/core_regions/scenes/missing.json"}}]}), encoding="utf-8")
    assert ai_cli._handle_apply_plan(_apply_args(broken)) == 1
    assert project_ownership.owned(root) is None
    lint = root.parent / "lint.json"  # refused by its lint, before anything runs
    lint.write_text(json.dumps({"wizard": "r4", "version": 1, "inputs": {}, "actions": [
        {"type": "create_scene", "args": {"path": "scenes/x.json"}, "description": "no template"}]}), encoding="utf-8")
    assert ai_cli._handle_apply_plan(_apply_args(lint)) == 1 and project_ownership.owned(root) is None

    before = _files(root)

    def unavailable(*_a: Any, **_k: Any) -> Any:
        raise project_ownership.OwnershipUnavailable("its ownership file can't be made (injected)")

    monkeypatch.setattr(project_ownership, "acquire", unavailable)
    assert ai_cli._handle_apply_plan(_apply_args(root.parent / "plan.json")) == 1
    assert ai_cli._handle_undo_last_plan(argparse.Namespace()) == 1
    assert capsys.readouterr().out.count("nothing was changed. its ownership file can't be made (injected)") == 2
    window = _Window()
    assert "[AI] ai_job: nothing was changed. its ownership file can't be made (injected)" in _ai_job(window, root.parent / "job.json")
    assert window.reloads == 0 and _files(root) == before


def test_a_plan_writes_only_inside_the_project_it_owns(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    other = tmp_path / "other"  # another project, beside this one and inside it: its owner isn't asked
    nested = root / "inner"
    for project in (other, nested):
        create_project(project, "Other", template_id="blank")
    monkeypatch.chdir(root)
    for world in (other / "worlds/main_world.json", nested / "worlds/main_world.json"):
        world.parent.mkdir(parents=True, exist_ok=True)
        world.write_text('{"scenes": {}}\n', encoding="utf-8")
        into = os.path.relpath(world, root)
        plan = tmp_path / "wire.json"
        plan.write_text(json.dumps({"wizard": "r4", "version": 1, "inputs": {"into_world": into}, "actions": [
            {"type": "wire_world", "description": "wire", "args": {"world_path": into, "scene_id": "x",
                                                                   "scene_path": "scenes/x.json"}}]}), encoding="utf-8")
        before = world.read_bytes()
        assert ai_cli._handle_apply_plan(_apply_args(plan, no_lint=True)) == 1
        assert "isn't in the project being changed" in capsys.readouterr().out
        assert world.read_bytes() == before and project_ownership.owned(root) is None


# ------------------------------------------------------------------------------------------- the console's ai_job
def test_ai_job_is_refused_in_a_window_that_edits_the_project(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    before = _files(root)
    held = SimpleNamespace(held=True)  # the window's own hold (mesh edit): for its editor, never a pass for ai_job
    for window, who in ((_Window(studio=object()), "Mesh Studio"), (_Window(project_ownership=held), "the editor"),
                        (_Window(editor_controller=SimpleNamespace(active=True)), "the editor")):
        said = _ai_job(window, root.parent / "job.json")
        assert said == [f"[AI] ai_job: nothing was changed. {who} has this project open in this window, and ai_job "
                        "would write its files behind your unsaved work. Ask an AI through Mesh Studio's AI panel (its "
                        "changes come to you to accept), or close it and run the job in the game."]
        assert window.reloads == 0 and _files(root) == before
    assert not (root / ".mesh/owner.lock").exists()  # (refused before anything, even asking)


def test_ai_job_in_a_game_window_is_refused_while_studio_has_the_project_and_works_once_closed(
        root: Path, studios: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    studio = studios(root)
    assert studio.start["ready"]
    studio.ask("edit Unsaved Warden")
    before, window = _files(root), _Window()
    said = _ai_job(window, root.parent / "job.json")
    assert said and said[0].startswith(f"[AI] ai_job: nothing was changed. {STUDIO_OPEN}")
    assert window.reloads == 0 and _files(root) == before
    assert studio.ask("save")["saved"] == [ROOM] and not list(root.rglob("*.outside-change*"))
    assert studio.close() == 0

    said = _ai_job(window, root.parent / "job.json")
    assert said[0].startswith("[AI] Applied 2 operation(s)") and window.reloads == 1
    scene = json.loads((root / ROOM).read_text(encoding="utf-8"))
    assert len(scene["lights"]) == 1 and "ai_quest" in (root / "assets/data/quests.json").read_text(encoding="utf-8")
    assert project_ownership.owned(root) is None


def test_ai_job_holds_the_project_while_it_writes_and_lets_it_go_however_it_ends(
        root: Path, studios: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    started, go = threading.Event(), threading.Event()

    class Paused(AIOps):
        def apply_job(self, job_payload: dict[str, Any]) -> dict[str, Any]:
            started.set()
            assert go.wait(60)
            return super().apply_job(job_payload)

    monkeypatch.setattr(handlers_ai, "AIOps", Paused)
    window, said = _Window(), []
    job = threading.Thread(target=lambda: said.extend(_ai_job(window, root.parent / "job.json")))
    job.start()
    try:
        assert started.wait(60)
        refused = studios(root)  # Studio opening meanwhile: turned away, nothing of the job's touched
        assert refused.start["ready"] is False and "An outside tool is writing" in refused.start["refused"]
    finally:
        go.set()
        job.join(60)
    assert said[0].startswith("[AI] Applied 2 operation(s)") and project_ownership.owned(root) is None

    monkeypatch.setattr(handlers_ai, "AIOps", AIOps)
    bad = root.parent / "bad.json"
    bad.write_text('{"operations": "not a list"}', encoding="utf-8")
    with pytest.raises(ValueError, match="job.operations must be a list"):
        _ai_job(window, bad)
    assert project_ownership.owned(root) is None  # (a job that raised let the project go)
