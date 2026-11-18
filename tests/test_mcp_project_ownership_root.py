"""#462 R5 remediation: MCP ``apply_ops`` (file fallback) and ``create_scene`` hold the lock of the project ``root``
is in, never one of ``root``'s own.

Independent review (Astra) of #522: given a ``root`` inside a project (an ordinary folder of it), the tools locked
that folder (``<folder>/.mesh/owner.lock``, a lock no editor takes). F1's check looks at the project and refuses while
an editor has it; but a Studio opening between the check and the lock, or another writer owning the project, didn't
stop the write. Now the check, the lock and every target are the project's (``project_ownership.ownership_root``,
``AIOps(project=...)``). The rule: tests/test_project_ownership_root.py.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
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
REGION = "packs/core_regions"
TOOLS: dict[str, Callable[[Path], dict[str, Any]]] = {
    "apply_ops": lambda root: tools.apply_ops([{"type": "set_world_start", "world_path": "worlds/main.json",
                                                "start_scene": "attic"}], root=str(root), validate=False),
    "create_scene": lambda root: tools.create_scene("scenes/attic", root=str(root)),
}
TARGET = {"apply_ops": f"{REGION}/worlds/main.json", "create_scene": f"{REGION}/scenes/attic.json"}
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

    def open_studio(root: Path, *args: str) -> StudioProcess:
        studio = StudioProcess(root, *args, log=tmp_path / f"studio_{len(started)}.log", env={"MESH_TEST_OWNER_WAIT": "0.3"})
        started.append(studio)
        assert studio.start["ready"], studio.start
        studio.ask("edit Unsaved Warden")
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def _files(root: Path) -> dict[str, str]:
    skip = ("owner.lock", "live_session.json")
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name not in skip}


def _after_the_check(work: Callable[[], dict[str, Any]], meanwhile: Callable[[], Any],
                     monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """``work`` (a tool call) paused right after F1's check answers; ``meanwhile`` (someone takes the project); go on."""
    checked, go = threading.Event(), threading.Event()
    check = tools._files_blocked

    def check_then_pause(r: str, tool: str) -> dict[str, Any] | None:
        verdict = check(r, tool)
        checked.set()
        assert go.wait(60)
        return verdict

    monkeypatch.setattr(tools, "_files_blocked", check_then_pause)
    result: list[dict[str, Any]] = []
    thread = threading.Thread(target=lambda: result.append(work()))
    thread.start()
    try:
        assert checked.wait(60)
        meanwhile()
    finally:
        go.set()
        thread.join(60)
    return result[0]


# ------------------------------------------------- 1. Studio owns the project; the tool's root is a folder inside it
@pytest.mark.parametrize("tool", list(TOOLS))
@pytest.mark.parametrize("bridge", ["live", "nobridge"])
def test_a_root_inside_a_project_studio_has_is_refused(outer: Path, studios: Any, tool: str, bridge: str) -> None:
    studio = studios(outer, *(["nobridge"] if bridge == "nobridge" else []))
    before = _files(outer)
    result = TOOLS[tool](outer / REGION)
    assert result["ok"] is False and result["reason"] in {"studio_open", "studio_session_uncertain"}, result
    assert _files(outer) == before and not (outer / REGION / ".mesh").exists()
    assert "Unsaved Warden" in studio.ask("state")["names"]


@pytest.mark.parametrize("tool", list(TOOLS))
def test_studio_opening_after_the_check_is_never_written_behind_through_an_inner_root(
        outer: Path, studios: Any, tool: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Astra's reproduction: the check passes (nothing has the project), Studio opens it and edits, the tool goes on.
    Before, the tool locked the inner folder and wrote; now it finds the project owned and writes nothing."""
    state: dict[str, Any] = {}

    def meanwhile() -> None:
        state["studio"] = studios(outer)
        state["before"] = _files(outer)

    result = _after_the_check(lambda: TOOLS[tool](outer / REGION), meanwhile, monkeypatch)
    assert result["ok"] is False and result["reason"] == "studio_open", result
    assert _files(outer) == state["before"] and not (outer / REGION / ".mesh").exists()
    assert "Unsaved Warden" in state["studio"].ask("state")["names"]


# ---------------------------------------------- 8. two writers of one project, from two folders: one lock, not two
@pytest.mark.parametrize("tool", list(TOOLS))
def test_a_writer_owning_the_project_stops_one_started_in_an_inner_folder(outer: Path, tool: str,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {}

    def meanwhile() -> None:  # writer A, another process, owns the project (mid-write)
        proc = subprocess.Popen([sys.executable, "-c", HOLD, str(REPO), str(outer), project_ownership.AUTHORING],
                                stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None and proc.stdout.readline().strip() == "held"
        state["a"], state["before"] = proc, _files(outer)

    try:
        result = _after_the_check(lambda: TOOLS[tool](outer / REGION), meanwhile, monkeypatch)
    finally:
        if "a" in state:
            state["a"].kill()
            state["a"].wait(timeout=30)
            state["a"].stdout.close()
    assert result["ok"] is False and result["reason"] == "project_busy", result
    assert _files(outer) == state["before"] and not (outer / REGION / ".mesh").exists()


# ----------------------------------------------- 2. Studio owns a nested project; the outer root aims into it
def test_the_outer_root_cant_change_a_nested_project_studio_has(outer: Path, studios: Any) -> None:
    studios(outer / "inner")
    before = _files(outer)
    into = tools.apply_ops([{"type": "set_world_start", "world_path": f"inner/{REGION}/worlds/main.json",
                             "start_scene": "x"}], root=str(outer), validate=False)
    assert into["ok"] is False and "another Mesh project than the one held" in into["results"][0]["message"]
    with pytest.raises(ValueError, match="another Mesh project than the one held"):
        tools.create_scene(f"inner/{REGION}/scenes/attic", root=str(outer))
    assert _files(outer) == before and project_ownership.owned(outer) is None


# ---------------------------------------- 5 + 6. inner folders and nested projects, each under the right lock
@pytest.mark.parametrize("tool", list(TOOLS))
def test_an_inner_root_works_under_the_projects_lock(outer: Path, tool: str, monkeypatch: pytest.MonkeyPatch) -> None:
    started, go = threading.Event(), threading.Event()
    name = "apply_job" if tool == "apply_ops" else "create_scene"
    original = getattr(AIOps, name)

    def paused(self: AIOps, *args: Any, **kwargs: Any) -> Any:
        started.set()
        assert go.wait(60)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AIOps, name, paused)
    result: list[dict[str, Any]] = []
    thread = threading.Thread(target=lambda: result.append(TOOLS[tool](outer / REGION)))
    thread.start()
    try:
        assert started.wait(60)
        assert (project_ownership.owned(outer, wait=0) or {}).get("kind") == project_ownership.AUTHORING
        assert not (outer / REGION / ".mesh").exists()  # the project's lock, not the folder's
    finally:
        go.set()
        thread.join(60)
    assert result[0]["ok"] is True and (outer / TARGET[tool]).is_file() and project_ownership.owned(outer) is None


@pytest.mark.parametrize("tool", list(TOOLS))
def test_a_nested_project_is_edited_under_its_own_ownership(outer: Path, studios: Any, tool: str) -> None:
    studio = studios(outer)  # Mesh Studio has the outer project; the nested one is free
    before_outer = {k: v for k, v in _files(outer).items() if not k.startswith("inner/")}
    result = TOOLS[tool](outer / "inner" / REGION)
    assert result["ok"] is True, result
    assert (outer / "inner" / TARGET[tool]).is_file()
    assert {k: v for k, v in _files(outer).items() if not k.startswith("inner/")} == before_outer
    assert project_ownership.owned(outer / "inner") is None and studio.ask("state")["unsaved"]
