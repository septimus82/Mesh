"""Watchfire R1, in real processes: a game played, saved and loaded, then the game started again normally (its own
main.py, a new process, the first session's saves and editor files present, no test flags: PYTEST_CURRENT_TEST is
taken out of the game's environment, so the editor's start-up restoration runs as it does for a player). The new game
has none of the first game's progress, and loading the save brings it back. On Mesh's starter template, in hidden
windows (tooling/watchfire_r1_sessions.py; the Watchfire project itself is played by its command line). Silent.
GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def sessions(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import watchfire_r1_sessions as r1

    out = tmp_path_factory.mktemp("r1")
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "r1", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    assert made.returncode == 0, made.stderr[-2000:]
    project = next(p.parent for p in out.rglob("config.json") if (p.parent / "main.py").is_file())
    os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
    return {"project": project, **r1.flag_sessions(project)}


def test_the_first_session_saves_and_loads_its_progress(sessions: dict) -> None:
    a = sessions["A"]
    assert "error" not in a, a
    assert a["new_game"]["story_flags"] == [] and a["saved"] and a["loaded"]
    assert a["after_load"]["story_flags"] == ["task_accepted", "watchfire_lit"]
    # A game no longer writes the editor's remembered scene (#422 H7: only editor launches read it); it wrote the save
    # slot here, which R1's restore must ignore (tests/test_new_game_isolation.py checks that guard with it written).
    assert sessions["files_after_A"]["session_last_scene_path"] is None


def test_a_new_game_after_it_starts_clean_and_the_save_still_loads(sessions: dict) -> None:
    b = sessions["B"]
    assert "error" not in b, b
    assert b["new_game"]["scene_loads"] and not any(p.startswith("saves/") for p in b["new_game"]["scene_loads"]), b
    assert b["new_game"]["story_flags"] == []
    assert b["loaded"] and b["after_load"]["story_flags"] == ["task_accepted", "watchfire_lit"]
