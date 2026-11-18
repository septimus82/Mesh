"""#462 R4 with Mesh Studio itself: the console's ``ai_job`` can't write the project behind Studio.

Studio takes every key while editing, but not in its play-test: there ` opens the game's console, as in any game
window. Before the fix ``ai_job`` typed there wrote the room and the quest file behind Studio's unsaved work, and
Studio's next save dropped the room's change (the quest stayed: half a job). A real hidden window, worked only
through the window's own input events. GL-gated: MESH_GL_SMOKE=1. The rest is tests/test_ai_write_paths.py.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from engine import authoring, optional_arcade
from engine.editor import project_ownership
from engine.project_scaffold import create_project
from tests.test_ai_write_paths import JOB, _files
from tests.test_studio_project_ownership import REPO, ROOM

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]
sys.path.insert(0, str(REPO / "tooling"))


def test_ai_job_typed_into_the_console_of_a_studio_play_test_changes_nothing(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    from hd2d_studio_demo import StudioDriver

    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")  # (no loopback server in a test)
    monkeypatch.setenv("MESH_RUNTIME_SETTINGS_PATH", str(tmp_path / "user_settings.json"))  # (never the checkout's)
    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    (root / "assets/data").mkdir(parents=True, exist_ok=True)
    (root / "assets/data/quests.json").write_text('{"quests": []}\n', encoding="utf-8")
    job = tmp_path / "job.json"
    job.write_text(json.dumps(JOB), encoding="utf-8")

    driver = StudioDriver(root)
    studio, window, key = driver.studio, driver.window, driver.arcade.key
    try:
        authoring.apply(studio.project, [{"op": "place_prefab", "prefab": "person", "x": 64, "y": 64},
                                         {"op": "rename_entity", "entity_id": "@0", "name": "Unsaved Warden"}])
        studio._reload()
        driver.advance()
        before = _files(root)
        driver.key(key.GRAVE)  # editing: Studio takes every key, the console doesn't open
        assert studio.mode == "edit" and not window.console_controller.active
        driver.key(key.F4)  # Play
        driver.key(key.GRAVE)
        assert studio.mode == "play" and window.console_controller.active  # the console, reachable here
        start = len(window.console_controller.lines)
        for ch in f"ai_job {job}":
            window.dispatch_event("on_text", ch)
        driver.key(key.ENTER)
        said = window.console_controller.lines[start:]
        assert any(line.startswith("[AI] ai_job: nothing was changed. Mesh Studio has this project open in this window")
                   for line in said), said
        assert _files(root) == before
        driver.key(key.GRAVE)
        driver.key(key.F4)  # Stop: the person's unsaved work as it was
        doc = studio.project.scene(studio.project.current)
        assert studio.mode == "edit" and studio.project.is_dirty
        assert [e.get("name") for e in doc["entities"]] == ["Player", "Unsaved Warden"] and not doc.get("lights")
        driver.key(key.S, key.MOD_CTRL)  # Save: exactly the person's work, nothing from outside to overwrite
        assert not studio.project.is_dirty and not list(root.rglob("*.outside-change*"))
        assert [str(e.get("name")) for e in json.loads((root / ROOM).read_text(encoding="utf-8"))["entities"]] == [
            "None", "Unsaved Warden"]
        assert (root / "assets/data/quests.json").read_text(encoding="utf-8") == '{"quests": []}\n'
    finally:
        studio.release_project()
        driver.close()
    assert project_ownership.owned(root) is None
