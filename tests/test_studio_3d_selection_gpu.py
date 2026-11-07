"""Watchfire R3, in Mesh Studio's real (hidden) window with its own mouse and keyboard events
(tooling/watchfire_r3_selection.py): a campfire is selected by clicking it; where things overlap, a click selects the
nearest and a click again without moving selects the one behind (a fire hidden by the cottage, two signs, two
campfires on one spot), the inspector following; a drag moves what is selected; right-click keeps it; empty ground
deselects; Sculpt, Paint and Scatter never select; undo, redo, save and reopen keep where things stand. Silent.
GL-gated: MESH_GL_SMOKE=1."""

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
def report(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import watchfire_r3_selection as r3

    out = tmp_path_factory.mktemp("r3")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    return r3.run(out)


def test_a_campfire_is_selected_by_clicking_it(report: dict) -> None:
    lone = report["1_click_lone_campfire"]
    assert lone["selected"] == "Campfire 1" and lone["inspector_name"] == "Campfire 1"
    assert lone["campfire_of_selected"]["enabled"] is True


def test_what_is_in_front_is_selected_first_and_a_click_again_selects_what_it_hides(report: dict) -> None:
    assert report["1b_under_hidden_fire"] == ["cottage", "Campfire 4"]
    assert report["1b_click_where_the_fire_is_hidden"]["structure"] == "cottage"
    assert "1 of 2 here" in report["1b_click_where_the_fire_is_hidden"]["message"]
    turned = report["1c_turn_the_selected_cottage"]
    assert turned["turned"][1] == 90.0 and turned["fire_unmoved"] and turned["structure"] == "cottage"
    assert report["1c_undo_turn"]["rotation"] in (None, 0, 0.0)
    hidden = report["1d_click_again_the_hidden_fire"]
    assert hidden["selected"] == "Campfire 4" and hidden["structure"] is None and hidden["inspector_name"] == "Campfire 4"


def test_two_overlapping_signs_take_turns_and_the_inspector_follows(report: dict) -> None:
    clicks = [report[f"2_signs_click_{k}"] for k in (1, 2, 3)]
    assert [c["under"] for c in clicks] == [["Sign", "Sign_1"]] * 3
    assert [c["selected"] for c in clicks] == ["Sign", "Sign_1", "Sign"]
    assert [c["inspector_name"] for c in clicks] == ["Sign", "Sign_1", "Sign"]
    assert "for the one behind" in clicks[0]["message"] and "for the front one again" in clicks[1]["message"]


def test_a_drag_moves_only_what_is_selected_and_undo_redo_follow(report: dict) -> None:
    drag = report["3_drag_selected"]
    assert drag["selected_before_drag"] == drag["selected"] == "Sign" and drag["moved"] == ["Sign"]
    assert report["3_undo"]["positions_restored"] and report["3_redo"]["positions_moved_again"]


def test_stacked_campfires_each_selected_in_turn_with_their_own_settings(report: dict) -> None:
    first, second = report["4_stack_click_1"], report["4_stack_click_2"]
    assert first["under"] == second["under"] == ["Campfire 2", "Campfire 3"]
    assert (first["selected"], first["campfire_of_selected"]["enabled"]) == ("Campfire 2", True)
    assert (second["selected"], second["campfire_of_selected"]["enabled"]) == ("Campfire 3", False)
    assert first["inspector_burning"][0] == "Burning: On" and second["inspector_burning"][0] == "Burning: Off"
    right = report["4_stack_right_click"]
    assert right["kept"] and right["selected"] == "Campfire 3" and "Delete" in right["menu"]


def test_empty_ground_deselects_and_terrain_brushes_never_select(report: dict) -> None:
    assert report["5_under_empty"] == []
    assert report["5_click_empty_ground"]["selected"] is None and report["5_click_empty_ground"]["structure"] is None
    for tool in ("sculpt", "paint", "scatter"):
        row = report[f"6_{tool}_click_on_campfire"]
        assert row["brush_on"] and row["selected"] is None and row["structure"] is None, tool


def test_save_and_reopen_keep_where_everything_stands(report: dict) -> None:
    assert report["7_saved"]["message"].startswith("Saved") and report["7_reopened"]["positions_match"]
