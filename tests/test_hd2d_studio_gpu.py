"""Milestone 16 Stage 5A: Mesh Studio's 3D view, worked through window input events like a person (hidden window):
open the lit HD-2D room in 3D, pick the structure (not the character), drag and turn it, undo, redo, save, reopen,
play-test with F4 and walk around it, stop, place a second copy from the project's models, and accept an AI's
proposal; transforms agree for drawing, picking and collision; Edit / Play / Edit frees the HD-2D renderer's GPU
objects. GL-gated: set MESH_GL_SMOKE=1."""

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
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),  # the game's own HUD prompt
    # Mesh Studio's existing text fields (engine/studio.py _field) still pass border colour/width the old way
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory, monkeypatch_module: None) -> dict:
    import hd2d_floors_demo
    import hd2d_studio_demo

    project = hd2d_floors_demo.build(tmp_path_factory.mktemp("studio") / "HD-2D studio")
    return hd2d_studio_demo.check(project, tmp_path_factory.mktemp("check"))


@pytest.fixture(scope="module")
def monkeypatch_module():
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"  # no loopback server for the AI bridge in a test
    yield
    os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def _step(run: dict, name: str) -> dict:
    return next(s for s in run["steps"] if s["step"] == name)


def test_the_hd2d_room_opens_in_studio_as_a_lit_3d_view(run: dict) -> None:
    opened = _step(run, "open")
    assert opened["active"] and opened["structures"] == ["crossing"]
    assert opened["lamps"] == 2 and opened["shadows"] and opened["left_panel_3d"] and opened["models_button"]


def test_picking_selects_characters_and_structures_apart(run: dict) -> None:
    pick = _step(run, "pick")
    assert pick["character_is_entity"] and pick["character"] == "start_player_128_128_0_0"
    assert pick["structure"] == "crossing" and pick["inspector"]


def test_drag_turn_undo_redo_save_and_reopen(run: dict) -> None:
    moved = _step(run, "move_and_turn")
    assert (moved["after_drag"]["x"], moved["after_drag"]["y"]) == (576.0, 416.0), "+2 m, +1 m, snapped"
    assert moved["after_turn"]["rotation"] == 90.0
    undo = _step(run, "undo_redo")
    assert undo["undo1"].get("rotation") is None and undo["undo2"] == moved["before"]
    assert undo["redo2"] == moved["after_turn"]
    assert _step(run, "save")["dirty_after"] is False
    reopened = _step(run, "reopen")
    assert {k: reopened["structure"][k] for k in ("x", "y", "rotation")} == {"x": 576.0, "y": 416.0, "rotation": 90.0}


def test_drawing_picking_and_collision_share_the_transform(run: dict) -> None:
    reopened = _step(run, "reopen")
    assert reopened["same_matrix"]
    assert list(reopened["floor_at_moved_platform"]) == [2.0, "crossing/col_platform_west"]
    assert reopened["drawn_top_at_moved_platform"] == 2.0


def test_play_walks_around_the_moved_structure_and_stop_returns_to_the_3d_view(run: dict) -> None:
    play = _step(run, "play")
    assert play["mode"] == "play" and play["hd2d"] and play["blocked_by_moved_structure"]
    assert all(w["standable"] for w in play["walk"]) and play["walk"][-1]["feet_m"][1] > 12.0
    stop = _step(run, "stop")
    assert stop["mode"] == "edit" and stop["active"]
    assert run["edit_renderer_objects"]["held_before_play"] > 20
    assert run["edit_renderer_objects"]["still_alive_after_stop"] == [], "every GPU object of the edit view was freed"


def test_placing_a_second_copy_keeps_its_collision_and_undoes(run: dict) -> None:
    placed = _step(run, "place_second_copy")
    assert placed["models_listed"] == ["assets/models/stone_crossing.glb"] and placed["preview_shown"]
    assert placed["new_id"] == "stone_crossing" and (placed["placed"]["x"], placed["placed"]["y"]) == (224.0, 640.0)
    assert "stone_crossing/col_bridge_deck" in placed["collision_floors"] and len(placed["collision_floors"]) == 7
    assert placed["after_undo"] is None and placed["after_redo"] == placed["placed"]


def test_an_ai_proposal_changes_structures_through_the_review(run: dict) -> None:
    ai = _step(run, "ai_proposal")
    assert any("places structure 'stone_crossing_2'" in line for line in ai["summary"])
    assert any("moves structure 'stone_crossing'" in line for line in ai["summary"])
    assert ai["accepted"]["copy"]["rotation"] == 180.0 and ai["accepted"]["third"]["id"] == "stone_crossing_2"
    assert ai["missing_model_refused"]["ok"] is False and "missing.glb" in ai["missing_model_refused"]["message"]
    # the AI's new structure covers the player's start: allowed, but Mesh Studio says so
    assert ai["accepted"]["newly_buried"] == ["Player"] and "Player can't stand there now" in ai["accepted"]["warning"]


def test_the_view_is_responsive(run: dict) -> None:
    perf = run["performance"]
    assert perf["draw_ms_median"] < 16 and perf["pick_ms_median"] < 5
