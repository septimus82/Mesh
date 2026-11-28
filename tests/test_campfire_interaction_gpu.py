"""Watchfire R2, in a real (hidden) game window: a campfire with no picture, given a conversation the way Mesh Studio
gives one, is talked to with the game's own keys (walk up to it, E); a picture-less object the world doesn't draw (a
trigger spot) with a conversation stays logic only. On the M23B clearing (tooling/m23b_fire_study.py). Silent.
GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
TRIGGER = (4.0, 2.6)  # m: a picture-less spot west of the campfire, nothing drawn there


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_RUNTIME_SETTINGS_PATH", str(tmp_path / "user_settings.json"))
    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")


def _said(game: Any) -> str | None:
    box = getattr(game.window.ui_controller, "dialogue_box", None)
    return str((box._current_entry or {}).get("text")) if box is not None and box.is_active() else None


def _walk_up_and_press_e(game: Any, x_m: float, y_m: float) -> str | None:
    """Stand two steps south of (x, y), walk north to it (the up arrow) and press E: what is said, if anything."""
    import m23b_fire_study as study

    keys = game.arcade.key
    player = game.player()
    player.center_x, player.center_y = x_m * study.PX, y_m * study.PX - 64.0
    game.step(2)
    for _ in range(120):
        if y_m * study.PX - player.center_y <= 36.0:
            break
        game.hold(keys.UP, 1)
    gap = (x_m * study.PX - player.center_x, y_m * study.PX - player.center_y)
    assert abs(gap[0]) < 8.0 and 0.0 < gap[1] <= 40.0, gap  # (there, facing it: well inside the 72 px reach)
    game.hold(keys.E, 2)
    game.step(5)
    return _said(game)


def test_a_campfire_without_a_picture_is_talked_to_and_a_trigger_spot_is_not(tmp_path: Path) -> None:
    import m23b_fire_study as study
    from hd2d_demo import HiddenGame

    from engine import project_ops as ops

    project = study.make_project(tmp_path, "r2_campfire")
    path = project / study.ROOM
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene = ops.set_dialogue_text(scene, ops.entity_ref(scene, "Campfire 1"), "The embers are still warm.")
    scene, spot = ops.place_blank(scene, "hills", "Trigger spot", TRIGGER[0] * study.PX, TRIGGER[1] * study.PX)
    scene = ops.set_dialogue_text(scene, spot, "Nothing is drawn here.")
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")

    game = HiddenGame(project, size=(1280, 720))
    try:
        game.window.audio.set_muted(True)
        game.load(study.ROOM)
        game.step(30)
        fire = game.sprite("Campfire 1")
        assert fire.visible is False and getattr(fire, "mesh_drawn", True) is False  # (no picture: the world draws it)

        assert _walk_up_and_press_e(game, *study.FIRE) == "The embers are still warm."
        for _ in range(4):  # (read on to the end)
            if _said(game) is None:
                break
            game.hold(game.arcade.key.E, 2)
            game.step(5)
        assert _said(game) is None

        assert _walk_up_and_press_e(game, *TRIGGER) is None  # (logic only: nothing there to talk to)
    finally:
        game.close()
