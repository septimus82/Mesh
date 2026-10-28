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
