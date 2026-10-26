"""Milestone 20A: sculpted ground in the real renderer and game loop, hidden windows (GL-gated: MESH_GL_SMOKE=1).

The Hills room (tooling/m20a_terrain_study.py builds it through project_ops.sculpt_terrain, as Studio and AI do): it
draws in the HD-2D view; the player walks over the hill, up the ramp, along the valley under the bridge, up the stairs
and across the bridge, and into the pond's basin, and the terrace's cliff stops him; sculpting moves nothing; a pond
whose shore is the ground holds its level in the basin; the ground casts shadows and rain lands on it; a click's ray
meets it; Mesh Studio sculpts it a click at a time with undo, redo, save and reopen; and in-place rebuilds and room
changes leave no GPU objects behind."""

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
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def test_the_player_walks_the_sculpted_ground_and_its_cliff_stops_him(tmp_path: Path) -> None:
    import m20a_terrain_study as study

    r = study.walking(tmp_path)
    hill = r["over_the_hill"]
    assert hill["reached"] == [True] and 1.4 < hill["highest_m"] <= 1.5 and hill["end_elevation_m"] < 0.1, hill
    ramp = r["up_the_ramp"]
    assert ramp["reached"] == [True] and abs(ramp["end_elevation_m"] - 1.5) < 0.01, ramp
    cliff = r["into_the_cliff"]
    assert cliff["reached"] == [False] and cliff["end_feet_m"][1] < 15.6 and cliff["highest_m"] < 0.6, cliff
    valley = r["along_the_valley_under_the_bridge"]
    assert valley["reached"] == [True] and valley["highest_m"] < -0.4, valley  # under the deck, never on it
    bridge = r["stairs_and_bridge"]
    assert bridge["reached"] == [True, True] and bridge["end_elevation_m"] >= 1.99, bridge  # over the valley
    pond = r["into_the_pond"]
    assert pond["reached"] == [True] and pond["end_elevation_m"] < -1.0, pond
    for row in r.values():  # always standing on what is there
        if row["floor"] == "ground":
            assert abs(row["end_elevation_m"] - row["ground_there_m"]) < 0.01, row


def test_sculpting_moves_nothing_and_says_what_it_left_out_of_place(tmp_path: Path) -> None:
    import m20a_terrain_study as study

    r = study.anchoring(tmp_path)
    assert r["moved"] == {"cottage": False, "Elder": False}, r
    assert r["left_out_of_place_by_the_edits"] == ["'cottage' is 0.6 m into the ground",
                                                    "'Elder' is 1.5 m above the ground"], r  # not the bridge: never on it
    assert r["settle_would_stand"] == ["start_elder"], r
    assert r["elder_can_stand_where_he_is"] is False, r


def test_a_pond_in_a_sculpted_basin_holds_its_own_level(tmp_path: Path) -> None:
    import m20a_terrain_study as study

    r = study.water(tmp_path)
    levels = r["water_pixels_by_level_m"]
    assert 0 < levels["-0.9"] < levels["-0.6"] < levels["-0.3"], r  # the shore follows the level
    assert r["drawn"] == r["drawn_with_its_depth_test_off"] > 10000, r  # submerged ground hides none of it
    assert r["rain_ring_pixels"] > 1000 and r["pixels_round_the_player_changed_by_water"] > 500, r
    assert r["mirrored_pixels_at_0_8"] > 5000, r


def test_the_ground_casts_shadows_takes_the_rain_and_is_picked_where_it_is(tmp_path: Path) -> None:
    import m20a_terrain_study as study

    r = study.environment(tmp_path)
    assert r["pixels_darkened_by_the_ground_s_own_shadows"] > 1000, r
    for row in r["rain_surface"]:
        if row["where"] == "under the bridge's deck":
            assert row["rain_stops_at_m"] > 1.8, row  # sheltered by the deck
        else:
            assert abs(row["rain_stops_at_m"] - row["ground_m"]) < 0.05, row
    assert r["picking_rays"] >= 10 and r["picking_height_error_m_max"] < 0.005, r


def test_studio_sculpts_a_click_at_a_time_with_undo_redo_save_and_reopen(tmp_path: Path) -> None:
    import m20a_terrain_study as study

    r = study.studio(tmp_path)
    assert r["cursor_on_the_ground_m"] is not None and r["raised_m"] > 0.3, r
    assert r["undone_to_before"] and r["redone_to_raised"] and r["saved_dirty_after"] is False, r
    assert r["reopened_same"] and r["play"] == {"mode": "play", "sculpted_ground": True} and r["after_stop"] == "edit", r


def test_rebuilding_in_place_and_room_changes_leave_nothing_behind(tmp_path: Path) -> None:
    import hd2d_visual_study as visual
    import m20a_terrain_study as study
    from hd2d_demo import _gl_counts

    game = study.open_room(tmp_path, "life")
    try:
        ctx = game.window.ctx
        terrain = game.window.hd2d_renderer.terrain
        chunks = [(i, j) for j in range(terrain.chunk_count()[1]) for i in range(terrain.chunk_count()[0])]
        counts = []
        for _ in range(4):  # (the first cycle: the game's own objects made once, its UI and the village's)
            hd = game.window.hd2d_renderer
            hd.update_terrain(hd.terrain, chunks)
            game.window.dispatch_event("on_draw")
            game.load(f"{visual.SCENES}/start.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            game.load(f"{visual.SCENES}/hills.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            ctx.gc()
            counts.append(_gl_counts(ctx))
        assert counts[1:] == counts[:-1] == [counts[1]] * 3, counts
        objects = game.window.hd2d_renderer.gl_objects()
        game.window.hd2d_renderer.release()
        assert all(getattr(getattr(o, "_glo", None), "value", 0) == 0 for o in objects)
    finally:
        game.close()


# --- Milestone 20B: live strokes in Mesh Studio (tooling/m20b_sculpt_study.py) ---------------------------------------

def test_studio_sculpts_live_one_stroke_one_undo_step(tmp_path: Path) -> None:
    import m20b_sculpt_study as study

    r = study.studio(tmp_path)
    s = r["stroke"]
    assert s["undo_steps_added"] == 1 and s["shown_equals_saved"] and s["raised_max_m"] > 0.1, s
    assert s["frame_ms"]["median"] < 60 and s["commit_ms"] < 200, s  # no room reload per click
    assert r["undo_gives_before"] and r["redo_gives_after"] and r["saved_dirty_after"] is False and r["reopened_same"], r
    for case in ("escape", "play_mid_stroke", "room_change_mid_stroke", "refused_upload"):
        assert r[case]["nothing_recorded"], (case, r[case])
    assert r["escape"]["ground_back"] and r["refused_upload"]["ground_back"], r
    assert r["play_mid_stroke"]["ground_is_saved"] and r["room_change_mid_stroke"]["ground_is_saved"], r
    c = r["controls"]
    assert c["shift_lowered"] and c["radius_px"] == [64.0, 80.0, 64.0] and c["picked_target_m"] is not None, c


def test_a_flat_room_s_first_stroke_and_its_undo(tmp_path: Path) -> None:
    import m20b_sculpt_study as study

    r = study.first_stroke_on_flat(tmp_path)
    assert r["before"] == {"sculpted": False} and r["after"]["sculpted"] and r["after"]["walk_world"], r
    assert r["undo_back_to_plain_ground"], r


def test_the_world_follows_a_live_edit(tmp_path: Path) -> None:
    import m20b_sculpt_study as study

    r = study.world(tmp_path)
    assert r["water"]["pixels_after"] != r["water"]["pixels_before"], r  # the shore moved
    assert r["shadow"]["pixels_darkened_west_of_the_mound"] > 1000, r  # no stale shadow
    assert r["room_box_top_m"]["after"] > r["room_box_top_m"]["before"], r
    assert abs(r["rain_stops_on_the_mound_m"] - r["shadow"]["mound_top_m"]) < 0.15, r
    walked = r["walked_onto_the_mound"]
    assert walked["elevation_m"] > 0.8 and abs(walked["elevation_m"] - walked["ground_m"]) < 0.01, r
    assert r["route_over_or_round_the_mound"]["points"] > 0 and r["chunk_edges_not_meeting"] == 0, r
