"""Milestone 22B: Mesh Studio's Ctrl+S while a field is being edited, and its scrolling left panel, with Studio's own
input events in a hidden window (tooling/studio_workflow_polish.py). GL-gated: MESH_GL_SMOKE=1."""

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
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _run(tmp_path_factory: pytest.TempPathFactory, phase: str) -> dict:
    import studio_workflow_polish

    out = tmp_path_factory.mktemp(f"m22b_{phase}")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        result: dict = getattr(studio_workflow_polish, phase)(out)
        return result
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


@pytest.fixture(scope="module")
def ctrl_s(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return _run(tmp_path_factory, "ctrl_s")


@pytest.fixture(scope="module")
def left(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return _run(tmp_path_factory, "left")


def test_ctrl_s_in_a_camera_field_commits_and_saves_once_and_it_reopens(ctrl_s: dict) -> None:
    camera = ctrl_s["camera"]
    assert camera["typed"]["field_focused"] and camera["typed"]["project_saves_on_ctrl_s"] == 1
    after = camera["after_ctrl_s"]
    assert after["message"] == "Saved 1 file(s)." and after["unsaved"] == []
    assert after["field_focused"] and after["field_text"] == "38"  # still the box typed in
    assert camera["on_disk_pitch"] == 38.0 and ctrl_s["reopened"]["pitch"] == 38.0
    assert camera["view_before"] == after["view"] == camera["view_after_frames"]  # S never moved the 3D view


def test_ctrl_s_in_a_sound_emitters_field_saves_it(ctrl_s: dict) -> None:
    sound = ctrl_s["sound"]
    assert sound["on_disk"] == {"in_file": True, "name": "Brook", "volume": 0.35}
    assert sound["after_ctrl_s"]["field_focused"] and sound["after_ctrl_s"]["message"] == "Saved 1 file(s)."


def test_invalid_text_and_ctrl_s_saves_nothing_and_keeps_what_was_typed(ctrl_s: dict) -> None:
    invalid = ctrl_s["invalid"]
    state = invalid["after_ctrl_s"]
    assert not state["message_ok"] and state["message"].startswith("Not saved. Volume: a number from 0 to 100.")
    assert state["field_text"] == "loud" and state["field_focused"]  # not lost, not marked done
    assert state["unsaved"] == ["meadow"]  # the rename waiting with it isn't written either
    assert invalid["on_disk"] == {"in_file": True, "name": "Brook", "volume": 0.35}
    assert ctrl_s["after_escape"]["field_text"] == "35" and ctrl_s["after_escape"]["message"] == "Put back as it was."
    saved = ctrl_s["saved_after_escape"]
    assert saved["on_disk"]["name"] == "Stream" and saved["state"]["unsaved"] == []
    assert ctrl_s["undo_after"] == {"name": "Brook", "unsaved": ["meadow"]}  # undo as before


@pytest.mark.parametrize("size", ["1280x720", "640x480"])
def test_the_left_panel_scrolls_to_every_tool_and_nothing_out_of_view_is_clickable(left: dict, size: str) -> None:
    entry = left[size]
    assert entry["below_count"] == 0 and not entry["last_object_in_ui_before_scrolling"]
    assert entry["click_below_the_window_armed"] is None
    wheel = entry["wheel_over_left"]
    assert wheel["left_scroll"] > 0 and wheel["view_unchanged"] and wheel["right_scroll_unchanged"]
    assert entry["reached_last_object"] == "extra_29"


def test_scrolled_out_buttons_have_no_tooltip_and_the_2d_palette_scrolls_on_its_own(left: dict) -> None:
    tip = left["tooltip_scrolled_out"]
    assert tip["over_it"] == "Turn the view 45 degrees (Q)" and tip["scrolled_out"]
    assert tip["over_where_it_was"] != tip["over_it"]
    palette = left["palette_2d"]
    (sheet0, left0), (sheet1, left1), (sheet2, left2) = palette["before"], palette["wheel_over_palette"], palette["wheel_over_rooms"]
    assert palette["palette_rows"][0] < palette["palette_rows"][1]
    assert sheet1[1] == sheet0[1] + 1 and left1 == left0  # the palette, not the panel
    assert left2 < left1 and sheet2 == sheet1  # the panel, not the palette
