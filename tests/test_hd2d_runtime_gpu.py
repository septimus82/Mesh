"""Milestone 16 Stage 2: an HD-2D room in the real game window (tooling/hd2d_demo.py's developer scene): the player,
moved by real key events through the ordinary controller, animates, is followed by the 3D camera, and is hidden by
the building when behind it; resizing and leaving the room release the renderer's GPU objects; batching draws the
same picture as unbatched with far fewer draw calls. Hidden window only. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    # the game's own interaction prompt (not HD-2D) draws with arcade.draw_text, which warns about its speed
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    import hd2d_demo

    return hd2d_demo.build(tmp_path_factory.mktemp("hd2d") / "HD-2D test")


@pytest.fixture(scope="module")
def walk(project: Path, tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_demo

    return hd2d_demo.check(project, tmp_path_factory.mktemp("check"))


def test_the_player_walks_animates_and_the_camera_follows(walk: dict) -> None:
    assert walk["hd2d_active"] and walk["error"] is None
    steps = {w["after"].split(" (")[0]: w for w in walk["walk"]}
    assert steps["right x40"]["player"][0] > steps["start"]["player"][0] + 80, "key events move the player"
    assert walk["walk_right_distinct_frames"] >= 3, "the walk animation plays"
    assert {w["animation"] for w in walk["walk"]} >= {"idle_down", "idle_right", "idle_up", "idle_left"}, "4 directions"
    for w in walk["walk"]:  # the camera's target settles on the player's feet (metres)
        assert abs(w["camera_target_m"][0] - w["player"][0] / 32) < 1.0


def test_the_building_hides_the_player_behind_it_and_not_in_front(walk: dict) -> None:
    steps = {w["after"].split(" (")[0]: w for w in walk["walk"]}
    front, behind = steps["start"], steps["up x46, left x40"]
    assert front["total_px"] > 1500 and front["visible_px"] == front["total_px"]
    assert behind["total_px"] > 1500 and behind["visible_px"] == 0
    assert behind["player"][1] > 330, "the platform's collision stopped them north of it, not inside it"
    assert walk["keeper_elevation_px"] == 32 and walk["keeper_visible_px"] > 1500, "the keeper stands on the platform"


def test_save_and_load_in_an_hd2d_room(walk: dict) -> None:
    assert walk["saved"] and walk["loaded"]
    sl = walk["save_load"]
    assert sl["after_load"] == sl["saved_at"] and sl["renderer_rebuilt"] and sl["keeper_elevation_px"] == 32


def test_resize_and_leaving_the_room_release_the_gpu_objects(walk: dict) -> None:
    assert walk["target_after_resize"] == [1280, 720]
    gl = walk["gl_objects"]
    assert walk["renderer_after_2d_room"] is None
    for kind in ("texture", "framebuffer", "program"):
        assert gl["after_2d_room"][kind] == gl["before"][kind], kind
    # A 2D room change itself costs a few buffers (unrelated to HD-2D); HD-2D adds none on top.
    plain_load = gl["after_another_2d_load"]["buffer"] - gl["after_2d_room"]["buffer"]
    assert gl["after_2d_room"]["buffer"] - gl["before"]["buffer"] <= plain_load


def test_static_batching_draws_the_same_picture_in_far_fewer_calls(project: Path, tmp_path: Path) -> None:
    import hd2d_demo
    from PIL import Image, ImageChops

    result = hd2d_demo.bench(project, tmp_path, frames=20)
    batched, unbatched = result["batched"], result["unbatched"]
    assert result["structures"] == 20 and batched["triangles"] == unbatched["triangles"]
    assert batched["draw_calls"] <= 8 < 200 <= unbatched["draw_calls"]
    a, b = Image.open(tmp_path / "village_batched.png"), Image.open(tmp_path / "village_unbatched.png")
    assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None
