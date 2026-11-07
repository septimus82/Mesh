"""Milestone 23A: Mesh Studio's responsive workspace, with its own input events in a hidden window
(tooling/studio_workspace.py creator): the tool categories, an object's inspector kept through them, Ctrl+S in a
focused box, Undo and Redo, Play and Stop, the panels hidden and shown, Focus, every window size in turn, and a 2D
project's tiles. GL-gated: MESH_GL_SMOKE=1."""

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


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import studio_workspace

    out = tmp_path_factory.mktemp("m23a")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        result: dict = studio_workspace.creator(out)
        return result
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_each_category_shows_its_own_tools_at_once(run: dict) -> None:
    steps = run["categories"]
    assert steps["terrain"]["sculpt_paint_scatter_in_view"]
    assert steps["paint"] == {"tool": "paint", "materials_in_view": True}
    assert steps["scatter"] == {"tool": "scatter", "meadow_in_view": True}
    assert steps["objects"] == {"person_in_view": True, "models_in_view": True, "scatter_still_armed": True}
    assert all(steps["environment"].values()) and all(steps["audio"].values())


def test_the_inspector_is_kept_through_categories_and_hidden_panels(run: dict) -> None:
    assert all(run["inspector_kept"].values()), run["inspector_kept"]


def test_ctrl_s_undo_redo_and_play_stop_still_work(run: dict) -> None:
    assert run["ctrl_s"] == {"message": "Saved 1 file(s).", "focused": True, "saved_name": "Elder Oak"}
    assert run["undo_redo"] == ["Elder", "Elder Oak"]
    assert run["play_stop"] == ["play", "edit", True]


def test_hiding_the_panels_and_focus_give_the_view_the_room(run: dict) -> None:
    panels = run["panels"]
    assert panels["view"] == [720] and panels["view_tools_hidden"] == 950 and panels["tools_hidden"]
    assert panels["view_focus"] == [1280, 650] and panels["focus_clean"] and panels["back"] == 720
    assert panels["wheel_over_panels_kept_the_view"]


@pytest.mark.parametrize("size", ["640x480", "1280x720", "1920x1080", "2560x1440"])
def test_every_size_keeps_a_usable_view_and_nothing_past_the_window(run: dict, size: str) -> None:
    at = run["sizes"][size]
    assert at["view"][0] >= 400 and at["past_the_window"] == [] and at["top_bar_past_edge"] == []
    if size == "640x480":
        assert 0 in at["panels"]  # (one panel at a time)


def test_a_2d_projects_tiles_are_picked_in_the_terrain_category(run: dict) -> None:
    tiles = run["tiles_2d"]
    assert tiles["tool"] == "paint" and tiles["brush"].startswith("Painting ")


@pytest.fixture(scope="module")
def safety(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import studio_workspace

    out = tmp_path_factory.mktemp("m23a_safety")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        result: dict = studio_workspace.safety(out)
        return result
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_tab_takes_a_typed_name_before_hiding_the_panels(safety: dict) -> None:
    case = safety["tab_valid"]
    assert case["before"]["text"] == "Elder Ash" and not case["before"]["focused"] and case["before"]["record"] == "Elder"
    assert case["after_tab"]["panels"] == [0, 0] and case["after_tab"]["record"] == "Elder Ash"
    assert case["after_tab_again"]["text"] == "Elder Ash"


def test_tab_waits_on_a_refused_name_and_keeps_it(safety: dict) -> None:
    case = safety["tab_refused"]
    for state in (case["after_tab"], case["after_tab_again"]):
        assert state["panels"] == [230, 330] and state["text"] == "   " and state["record"] == "Elder"
        assert not state["message_ok"] and state["message"].startswith("A name can't be empty. Correct the box")


def test_a_category_switch_waits_on_a_refused_brush_box_and_goes_on_with_a_valid_one(safety: dict) -> None:
    refused = safety["category_refused"]
    for state in (refused["after_switch"], refused["back_on_terrain"]):
        assert state["left_tab"] == "terrain" and state["shown"] and state["text"] == "big"
        assert not state["message_ok"] and state["message"].startswith("Type a number.")
    assert refused["after_switch"]["message"].endswith("until then nothing else is done.")
    assert refused["radius"] == [64.0, 64.0]
    assert safety["category_valid"] == {"left_tab": "objects", "radius": 96.0}


@pytest.mark.parametrize(("case", "text"), [("resize_valid", "Elder Birch"), ("resize_refused", "   ")])
def test_a_resize_keeps_what_is_typed_uncommitted(safety: dict, case: str, text: str) -> None:
    state = safety[case]["after_resize"]
    assert state["shown"] and state["text"] == text and state["record"] == "Elder"  # still to commit
