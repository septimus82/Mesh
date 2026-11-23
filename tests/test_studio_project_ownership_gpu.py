"""#462 R2 with Mesh Studio itself: one writable Studio per project, each Studio a real process with a real (hidden)
window (``engine.studio.open_studio``, through ``tests/studio_owner_process.py real``), and ``mesh edit`` as the
launcher runs it. The outside tool is ``engine.authoring_session``, in this process.
GL-gated: MESH_GL_SMOKE=1. The same cases without a window, and the rest, are tests/test_studio_project_ownership.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from engine import authoring_session, optional_arcade
from engine.editor import project_ownership
from engine.editor.live_session_bridge import session_file_path
from engine.project_scaffold import create_project
from tests.test_studio_project_ownership import ADD_SEXTON, REPO, ROOM, StudioProcess, _files, _on_disk

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


@pytest.fixture
def studios(tmp_path: Path) -> Iterator[Any]:
    """``open(root, *args)`` starts Mesh Studio (a real hidden window) in its own process; all are ended at the end."""
    started: list[StudioProcess] = []
    settings = str(tmp_path / "user_settings.json")  # (each Studio's own settings file: never the checkout's)

    def open_studio(root: Path, *args: str) -> StudioProcess:
        # (its live session on, or off: as a person starts Mesh Studio, by the variable it is started with)
        env = {"MESH_TEST_OWNER_WAIT": "0.3", "MESH_RUNTIME_SETTINGS_PATH": settings, "PYTHONPATH": str(REPO),
               "MESH_STUDIO_NO_AI_BRIDGE": "1" if "nobridge" in args else None}
        studio = StudioProcess(root, "real", *args, log=tmp_path / f"studio_{len(started)}.log", env=env)
        started.append(studio)
        return studio

    yield open_studio
    for studio in started:
        if studio.proc.poll() is None:
            studio.proc.kill()
        studio.end()


def test_one_mesh_studio_has_a_project_and_a_second_is_turned_away_without_touching_it(root: Path, studios: Any) -> None:
    a = studios(root)
    assert a.start["ready"]
    a.ask("edit Unsaved Warden")
    before, record = _files(root), session_file_path(root).read_bytes()

    # the launcher's way in (``mesh edit``): refused before a window opens, with the exit code the launcher reads
    launched = subprocess.run([sys.executable, "-m", "mesh_cli", "edit", str(root)], cwd=REPO, capture_output=True,
                              text=True, timeout=180, env={**os.environ, "PYTHONPATH": str(REPO)})
    assert launched.returncode == project_ownership.EXIT_OPEN_ELSEWHERE, launched.stdout[-800:] + launched.stderr[-800:]
    assert "This project is already open in Mesh Studio. Use the window that has it" in launched.stdout
    b = studios(root)  # and Studio opened directly (``open_studio``)
    assert b.start["ready"] is False and "already open in Mesh Studio" in b.start["refused"]

    assert session_file_path(root).read_bytes() == record  # A's record as it was
    state = authoring_session.studio_state(root)
    assert state["state"] == "live" and state["host"] == "mesh_studio"
    assert state["info"]["session_id"] == a.start["session_id"]
    assert "proposed there" in authoring_session.apply(root, ADD_SEXTON)["note"]  # an outside change goes to A
    assert _files(root) == before
    held = a.ask("state")
    assert "Unsaved Warden" in held["names"] and held["unsaved"] and held["pending"] == ["Changes from an AI"]
    assert a.ask("accept")["result"]["ok"]
    saved = a.ask("save")
    assert saved["saved"] == [ROOM], saved  # (the whole answer: its "error" says why a save failed)
    assert sorted(n for n in _on_disk(root) if n != "None") == ["Sexton", "Unsaved Warden"]
    assert not list(root.rglob("*.outside-change.bak"))

    assert a.close() == 0  # the window closed: the session's record removed, the project let go
    assert not session_file_path(root).exists() and project_ownership.owned(root) is None
    assert authoring_session.studio_state(root) == {"state": "none"}
    c = studios(root)  # another Studio opens it
    assert c.start["ready"] and c.ask("state")["names"].count("Sexton") == 1
    assert c.close() == 0


def test_a_mesh_studio_with_its_live_session_off_and_one_that_crashed(root: Path, studios: Any) -> None:
    quiet = studios(root, "nobridge")  # MESH_STUDIO_NO_AI_BRIDGE: no bridge, no record; the project is still its own
    assert quiet.start["ready"] and quiet.start["session_id"] is None and not session_file_path(root).exists()
    quiet.ask("edit Unsaved Warden")
    before = _files(root)
    state = authoring_session.studio_state(root)
    assert state["state"] == "uncertain" and state["problem"]["reason"] == "owned_without_session"
    assert authoring_session.apply(root, ADD_SEXTON)["reason"] == "studio_session_uncertain" and _files(root) == before
    assert quiet.close() == 0 and project_ownership.owned(root) is None

    crashed = studios(root)
    assert crashed.start["ready"]
    crashed.kill()  # the process gone: its record stays, its hold on the project does not
    assert session_file_path(root).is_file() and project_ownership.owned(root) is None
    state = authoring_session.studio_state(root)
    assert state["state"] == "uncertain" and state["problem"]["owned"] is False
    assert authoring_session.apply(root, ADD_SEXTON)["reason"] == "studio_session_uncertain" and _files(root) == before
    again = studios(root)  # the project isn't locked for good: Studio opens it, and its session is the record now
    assert again.start["ready"]
    state = authoring_session.studio_state(root)
    assert state["state"] == "live" and state["info"]["session_id"] == again.start["session_id"]
    assert again.close() == 0
