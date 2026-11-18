"""#462 R5: MCP ``apply_ops``' direct-file fallback and ``create_scene`` own the project while they write.

Before: both checked that no editor had the project open (``tools._files_blocked``, F1), then wrote with nothing
held. Mesh Studio opening between the check and the write read the files, and the write then landed behind it
(world, quests, cutscenes, a new scene: each reproduced). Now they own the project (R2's OS lock) from after the
check until the write and the validation are done; a Studio opening meanwhile waits, then is turned away.

Every Studio and every second writer here is its own process (``tests/studio_owner_process.py``, ``python -c``): the
real OS lock. Each write path on its own: the world, quests, cutscenes (``apply_ops``) and ``create_scene``.
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
from typing import Any

import pytest

from engine.ai_ops import AIOps
from engine.editor import project_ownership
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from tests.test_studio_project_ownership import REPO, StudioProcess

pytestmark = pytest.mark.integration  # (F13-A: subprocesses, OS locks)
SCENE = "packs/core_regions/scenes/attic"
PATHS: dict[str, tuple[str, Callable[[str], Any], str]] = {  # label: (tool, its argument given the world file, target)
    "world": ("apply_ops", lambda world: [{"type": "set_world_start", "world_path": world, "start_scene": "attic",
                                           "start_spawn": "door"}], "WORLD"),
    "quests": ("apply_ops", lambda world: [{"type": "add_quest_definition", "quest_id": "ai_quest",
                                            "quest": {"title": "From the AI"}}], "assets/data/quests.json"),
    "cutscenes": ("apply_ops", lambda world: [{"type": "add_cutscene", "id": "ai_scene",
                                               "steps": [{"type": "wait", "seconds": 1}]}], "cutscenes.json"),
    "create_scene": ("create_scene", lambda world: SCENE, SCENE + ".json"),
}
CALL = """
import json, sys, time, pathlib
sys.path.insert(0, sys.argv[1])
from engine.mcp_server import tools
root, label, gate = sys.argv[2], sys.argv[3], sys.argv[4]
paths = {k: v for k, v in json.loads(sys.argv[5]).items()}
print("ready", flush=True)
while gate and not pathlib.Path(gate).exists():
    time.sleep(0.005)
tool, arg = paths[label]
result = tools.apply_ops(arg, root=root, validate=False) if tool == "apply_ops" else tools.create_scene(arg, root=root)
print("result " + json.dumps({"ok": result.get("ok"), "reason": result.get("reason"), "message": result.get("message")}), flush=True)
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    (path / "assets/data").mkdir(parents=True, exist_ok=True)
    (path / "assets/data/quests.json").write_text('{"quests": {}}\n', encoding="utf-8")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    started: list[StudioProcess] = []

    def open_studio(root: Path, *args: str, wait: str = "0.3", gate: str = "") -> StudioProcess:
        env = {"MESH_TEST_OWNER_WAIT": wait, **({"MESH_TEST_START_GATE": gate} if gate else {})}
        studio = StudioProcess(root, *args, log=tmp_path / f"studio_{len(started)}.log", env=env)
        started.append(studio)
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _world(root: Path) -> str:
    return str(json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])


def _target(root: Path, label: str) -> Path:
    target = PATHS[label][2]
    return root / (_world(root) if target == "WORLD" else target)


def _call(root: Path, label: str) -> dict[str, Any]:
    tool, arg, _ = PATHS[label]
    if tool == "apply_ops":
        return tools.apply_ops(arg(_world(root)), root=str(root), validate=False)
    return tools.create_scene(arg(_world(root)), root=str(root))


def _paths_json(root: Path) -> str:
    return json.dumps({k: [tool, arg(_world(root))] for k, (tool, arg, _) in PATHS.items()})


def _files(root: Path) -> dict[str, str]:
    skip = {".mesh/owner.lock", ".mesh/live_session.json"}
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.relative_to(root).as_posix() not in skip}


def _pause(monkeypatch: pytest.MonkeyPatch, label: str) -> tuple[threading.Event, threading.Event]:
    """The tool's write paused once it has begun (inside the ownership, if it holds one)."""
    started, go = threading.Event(), threading.Event()
    name = "apply_job" if PATHS[label][0] == "apply_ops" else "create_scene"
    original = getattr(AIOps, name)

    def paused(self: AIOps, *args: Any, **kwargs: Any) -> Any:
        started.set()
        assert go.wait(60)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AIOps, name, paused)
    return started, go


def _in_thread(work: Callable[[], Any]) -> tuple[threading.Thread, list[Any]]:
    out: list[Any] = []
    thread = threading.Thread(target=lambda: out.append(work()))
    thread.start()
    return thread, out


# --------------------------------------------------------------------------------- Studio open: refused, untouched
@pytest.mark.parametrize("label", list(PATHS))
@pytest.mark.parametrize("bridge", ["live", "nobridge"])
def test_refused_while_studio_holds_unsaved_edits(root: Path, studios: Any, label: str, bridge: str) -> None:
    studio = studios(root, *(["nobridge"] if bridge == "nobridge" else []))
    assert studio.start["ready"]
    studio.ask("edit Unsaved Warden")
    before = _files(root)
    result = _call(root, label)
    assert result["ok"] is False
    assert result["reason"] == ("studio_open" if bridge == "live" else "studio_session_uncertain")
    assert _files(root) == before  # byte-identical: nothing read as current, nothing written
    held = studio.ask("state")
    assert "Unsaved Warden" in held["names"] and held["unsaved"]
    assert studio.close() == 0


@pytest.mark.parametrize("label", list(PATHS))
def test_studio_opening_between_the_check_and_the_write_is_never_written_behind(
        root: Path, studios: Any, label: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The reproduction: the check passes (nothing has the project), Studio opens and edits, then the tool goes on.
    Before the fix the write landed behind Studio; now the tool finds the project owned and writes nothing."""
    checked, go = threading.Event(), threading.Event()
    check = tools._files_blocked

    def check_then_pause(r: str, tool: str) -> dict[str, Any] | None:
        verdict = check(r, tool)
        checked.set()
        assert go.wait(60)
        return verdict

    monkeypatch.setattr(tools, "_files_blocked", check_then_pause)
    writer, result = _in_thread(lambda: _call(root, label))
    try:
        assert checked.wait(60)
        studio = studios(root)
        assert studio.start["ready"]  # (the check said free, and nothing held it: Studio opened)
        studio.ask("edit Unsaved Warden")
        before = _files(root)
    finally:
        go.set()
        writer.join(60)
    assert result[0]["ok"] is False and result[0]["reason"] == "studio_open", result
    assert _files(root) == before
    assert "Unsaved Warden" in studio.ask("state")["names"] and studio.close() == 0


# ------------------------------------------------------------------------------ while it writes: owned throughout
@pytest.mark.parametrize("label", list(PATHS))
def test_studio_opening_during_a_permitted_write_waits_until_it_is_done(
        root: Path, studios: Any, label: str, monkeypatch: pytest.MonkeyPatch) -> None:
    started, go = _pause(monkeypatch, label)
    writer, result = _in_thread(lambda: _call(root, label))
    opener, opened = _in_thread(lambda: studios(root, wait="60"))  # (Studio waits for the project, up to a minute)
    try:
        assert started.wait(60)
        time.sleep(1.5)
        assert not opened and opener.is_alive()  # still waiting: the tool owns the project mid-write
        assert (project_ownership.owned(root, wait=0) or {}).get("kind") == project_ownership.AUTHORING
    finally:
        go.set()
        writer.join(60)
        opener.join(120)
    assert result[0]["ok"] is True and _target(root, label).is_file()
    studio = opened[0]
    assert studio.start["ready"]  # opened once the write was done and the project let go
    assert _target(root, label).stat().st_mtime <= (project_ownership.owned(root) or {})["since"]
    assert studio.close() == 0


@pytest.mark.parametrize("label", list(PATHS))
def test_a_second_mcp_writer_is_turned_away_while_one_writes(root: Path, label: str,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    started, go = _pause(monkeypatch, "world")  # writer A: this process, mid-write on the world
    writer, result = _in_thread(lambda: _call(root, "world"))
    try:
        assert started.wait(60)
        before = _files(root)
        second = subprocess.run([sys.executable, "-c", CALL, str(REPO), str(root), label, "", _paths_json(root)],
                                capture_output=True, text=True, timeout=180)
        answer = json.loads(next(line[7:] for line in second.stdout.splitlines() if line.startswith("result ")))
        # (refused at the check, F1: owned with no session is "an outside tool is writing"; or, past it, by the lock)
        assert answer["ok"] is False, second.stdout[-800:] + second.stderr[-800:]
        assert (answer["reason"], "writing" in answer["message"]) in {("studio_session_uncertain", True),
                                                                       ("project_busy", True)}, answer
        assert _files(root) == before
    finally:
        go.set()
        writer.join(60)
    assert result[0]["ok"] is True and project_ownership.owned(root) is None


@pytest.mark.parametrize("label", list(PATHS))
def test_studio_and_an_mcp_write_started_at_once_never_overlap(root: Path, tmp_path: Path, label: str,
                                                                studios: Any) -> None:
    """Started at the same instant, twice: either the tool was refused and wrote nothing, or Studio took the project
    only after the tool's write (its ownership began after the file's last change)."""
    for attempt in range(2):
        target = _target(root, label)
        if label == "create_scene" and target.exists():
            target.unlink()  # (a fresh scene each time: this test made it)
        gate = tmp_path / f"gate_{label}_{attempt}"
        writer = subprocess.Popen([sys.executable, "-c", CALL, str(REPO), str(root), label, str(gate),
                                   _paths_json(root)], stdout=subprocess.PIPE, text=True)
        try:
            assert writer.stdout is not None and writer.stdout.readline().strip() == "ready"
            before = _files(root)
            opener, opened = _in_thread(lambda: studios(root, wait="10", gate=str(gate)))
            time.sleep(0.2)  # (both waiting at the gate)
            gate.write_text("go", encoding="utf-8")
            answer = json.loads(next(line[7:] for line in writer.stdout if line.startswith("result ")))
            opener.join(120)
            studio = opened[0]
            assert studio.start["ready"]
            since = (project_ownership.owned(root) or {})["since"]
            if answer["ok"]:
                assert target.stat().st_mtime <= since, "Studio owned the project before the tool's write"
            else:
                assert answer["reason"] == "studio_open" and _files(root) == before
            assert studio.close() == 0
        finally:
            writer.kill()
            writer.wait(timeout=30)
            assert writer.stdout is not None
            writer.stdout.close()


# ------------------------------------------------------------------------- failures and interruptions let it go
def test_failed_raising_and_killed_writes_let_the_project_go(root: Path, studios: Any,
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tools.apply_ops([{"type": "edit_quest", "quest_id": "q", "patch": {}, "quests_path": "nope.json"}],
                              root=str(root), validate=False)
    assert missing["ok"] is False and project_ownership.owned(root) is None  # an operation that failed

    def boom(self: AIOps, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("injected")

    with monkeypatch.context() as patch:
        patch.setattr(AIOps, "create_scene", boom)
        with pytest.raises(RuntimeError, match="injected"):
            tools.create_scene(SCENE, root=str(root))
    assert project_ownership.owned(root) is None  # a write that raised

    killed = subprocess.Popen([sys.executable, "-c", (
        "import sys, time; sys.path.insert(0, sys.argv[1]); from engine.ai_ops import AIOps; "
        "AIOps.apply_job = lambda self, job: (print('writing', flush=True), time.sleep(60)); "
        "from engine.mcp_server import tools; tools.apply_ops([{'type': 'set_world_start', 'start_scene': 'x'}], "
        "root=sys.argv[2], validate=False)"), str(REPO), str(root)], stdout=subprocess.PIPE, text=True)
    try:
        assert killed.stdout is not None and any(line.strip() == "writing" for line in killed.stdout)
        assert (project_ownership.owned(root, wait=0) or {}).get("kind") == project_ownership.AUTHORING
    finally:
        killed.kill()  # interrupted: none of its own code runs
        killed.wait(timeout=30)
        assert killed.stdout is not None
        killed.stdout.close()
    assert project_ownership.owned(root) is None
    studio = studios(root)
    assert studio.start["ready"] and studio.close() == 0


@pytest.mark.parametrize("label", list(PATHS))
def test_an_ownership_that_cant_be_established_is_a_refusal(root: Path, label: str,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    before = _files(root)
    for failure in (project_ownership.OwnershipUnavailable("no locks on this file system (injected)"),
                    RuntimeError("something unexpected (injected)")):
        def refuse(*_a: Any, _f: Exception = failure, **_k: Any) -> Any:
            raise _f

        monkeypatch.setattr(project_ownership, "acquire", refuse)
        result = _call(root, label)
        assert result["ok"] is False and result["reason"] == "ownership_unknown" and "(injected)" in result["message"]
        assert _files(root) == before


# ------------------------------------------------------------------------------- Studio closed: as before, owned
@pytest.mark.parametrize("label", list(PATHS))
def test_with_studio_closed_each_write_succeeds_and_lets_the_project_go(root: Path, studios: Any, label: str) -> None:
    before = _files(root)
    result = _call(root, label)
    assert result["ok"] is True, result
    changed = {k for k in set(before) | set(_files(root)) if before.get(k) != _files(root).get(k)}
    assert changed == {_target(root, label).relative_to(root).as_posix()}
    assert project_ownership.owned(root) is None
    studio = studios(root)
    assert studio.start["ready"] and studio.close() == 0


def test_writes_stay_in_the_owned_project(root: Path, tmp_path: Path) -> None:
    inner = root / "inner"  # another project inside this one: its owner is not the one held
    create_project(inner, "Inner", template_id="blank")
    (inner / "worlds").mkdir(exist_ok=True)
    (inner / "worlds/main.json").write_text('{"scenes": {}}\n', encoding="utf-8")
    before = _files(root)
    into_inner = tools.apply_ops([{"type": "set_world_start", "world_path": "inner/worlds/main.json",
                                   "start_scene": "x"}], root=str(root), validate=False)
    assert into_inner["ok"] is False and "another project inside this one" in into_inner["results"][0]["message"]
    with pytest.raises(ValueError, match="another project inside this one"):  # (as a path outside always has)
        tools.create_scene("inner/scenes/attic", root=str(root))
    with pytest.raises(ValueError, match="escapes workspace"):
        tools.create_scene(os.path.relpath(tmp_path / "elsewhere", root), root=str(root))
    assert _files(root) == before and not (tmp_path / "elsewhere.json").exists()
    assert project_ownership.owned(root) is None
