"""Milestone 19A: puddles and ponds in the real renderer, hidden windows (GL-gated: MESH_GL_SMOKE=1).

The starter village with a puddle beside the cottage and a pond near the bridge (tooling/m19_water_study.py builds it
through project_ops, as Studio and AI do): the water is depth-tested (the shop's roof hides part of the pond) and moves
with the world; rain rings it, and not under the bridge's deck (Stage 18B's precipitation map); the player's steps
through the puddle splash and announce themselves; a pond set not walkable stops the player; a 2D room draws its water
under its characters; the GPU objects stay level over room changes; and the whole Studio workflow, through its own
buttons, fields and keys."""

from __future__ import annotations

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
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def test_water_is_depth_tested_and_moves_with_the_world(tmp_path: Path) -> None:
    import m19_water_study as study

    r = study.depth_and_anchoring(tmp_path)
    assert r["pond_pixels_drawn"] > 20000 and r["pond_pixels_hidden_by_structures"] > 500, r
    assert r["water_pixels_found_where_the_world_moved"] > 0.95, r


def test_rain_rings_open_water_and_not_water_under_shelter(tmp_path: Path) -> None:
    import m19_water_study as study

    r = study.ripples(tmp_path)
    assert min(r["puddle"]["ripple_pixels_per_frame"]) > 300 and min(r["pond"]["ripple_pixels_per_frame"]) > 3000, r
    sheltered, control = r["sheltered"]["ripple_pixels_per_frame"], r["sheltered_negative_control_shelter_off"]["ripple_pixels_per_frame"]
    assert sum(sheltered) < 0.35 * sum(control), r  # its rim reaches out from under the deck; the rest stays calm
    rings = r["rings_follow_the_world"]
    assert rings["overlap_at_best"] > 0.85 and rings["overlap_unshifted"] < 0.5 and rings["best_shift_px"] < -10, r


def test_steps_through_a_puddle_splash_and_announce_themselves(tmp_path: Path) -> None:
    import m19_water_study as study

    r = study.footsteps(tmp_path)
    assert r["steps_through_the_puddle"] >= 3 and r["water_step_events_seen"] == r["steps_through_the_puddle"], r


def test_a_pond_can_be_waded_or_block_the_way(tmp_path: Path) -> None:
    import m19_water_study as study

    r = study.blocking(tmp_path)
    assert r["walkable"]["feet_reached_m"] > r["walkable"]["pond_south_edge_m"] + 1.0, r
    assert r["blocking"]["feet_reached_m"] < r["blocking"]["pond_south_edge_m"] + 0.1, r


def test_a_2d_room_draws_its_water_under_its_characters(tmp_path: Path) -> None:
    import m19_water_study as study

    r = study.two_d(tmp_path)
    assert r["water_pixels"] > 5000 and r["player_pixels_changed_by_water"] == 0, r


def test_room_changes_and_release_keep_gpu_objects_level(tmp_path: Path) -> None:
    import hd2d_visual_study as visual
    import m19_water_study as study
    from hd2d_demo import _gl_counts

    game = visual.HiddenGame(study.make_project(tmp_path, "life"), size=visual.SIZE)
    try:
        ctx, counts = game.window.ctx, []
        for _ in range(4):
            game.load(f"{visual.SCENES}/cottage.json")
            game.step(3)
            game.draw()
            game.load(f"{visual.SCENES}/start.json")
            game.step(3)
            game.draw()
            assert game.window.hd2d_renderer.water is not None and game.window.hd2d_renderer.water.count == 2
            ctx.gc()
            counts.append({k: v for k, v in _gl_counts(ctx).items() if k != "buffer"})
        assert counts[1:] == counts[:-1], counts
        hd = game.window.hd2d_renderer
        objects = hd.water.gl_objects()
        hd.water.release()
        hd.water.release()  # a second release does nothing
        assert all(getattr(getattr(o, "_glo", None), "value", 0) == 0 for o in objects)
    finally:
        game.close()


def test_a_creator_adds_and_edits_water_in_studio(tmp_path: Path) -> None:
    import m19_water_study as study

    r = study.studio_workflow(tmp_path)
    assert r["placed"]["water"]["preset"] == "puddle", r
    assert r["pond_180"] == {"preset": "pond", "width": 180.0} and r["undo_redo_width"][1] == 180.0, r
    assert r["undo_redo_width"][0] != 180.0, "undo took the width back"
    assert r["drawn_in_editing_view"]["water_surfaces"] == 1 and r["drawn_in_editing_view"]["moving"] > 500, r
    assert r["clicked_in_3d_selects_it"] and r["saved_dirty_after"] is False, r
    assert r["reopened"]["preset"] == "pond" and r["reopened"]["width"] == 180.0, r
    assert r["in_play"] == {"mode": "play", "water_surfaces": 1} and r["after_stop_mode"] == "edit", r


def test_water_layer_that_fails_part_way_leaves_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hd2d_visual_study as visual
    from hd2d_demo import _gl_counts

    from engine.water import WaterLayer

    game = visual.HiddenGame(visual.new_project(tmp_path, "fail", stage6a=False), size=visual.SIZE)
    try:
        game.load(f"{visual.SCENES}/start.json")
        ctx = game.window.ctx
        ctx.gc()
        before = _gl_counts(ctx)

        def refuse(*_: Any, **__: Any) -> Any:
            raise RuntimeError("no buffer (injected)")

        monkeypatch.setattr(ctx, "buffer", refuse)
        with pytest.raises(RuntimeError, match="injected"):
            WaterLayer(ctx, gl=game.arcade.gl)
        monkeypatch.undo()
        ctx.gc()
        assert _gl_counts(ctx) == before
    finally:
        game.close()


def test_a_driver_refusing_the_water_turns_it_off_for_the_room_not_the_game(tmp_path: Path,
                                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    import hd2d_visual_study as visual
    import m19_water_study as study
    from hd2d_demo import _gl_counts

    game = visual.HiddenGame(study.make_project(tmp_path, "refuse", rain=False), size=visual.SIZE)
    try:
        game.load(f"{visual.SCENES}/start.json")
        game.step(30)
        hd, ctx = game.window.hd2d_renderer, game.window.ctx
        bodies = game.window.water_bodies
        game.window.water_bodies = []
        game.draw()  # the frame's own target made first
        game.window.water_bodies = bodies
        ctx.gc()
        before = _gl_counts(ctx)

        def refuse(*_: Any, **__: Any) -> Any:
            raise RuntimeError("no depth texture (injected)")

        monkeypatch.setattr(ctx, "depth_texture", refuse)
        for _ in range(3):
            assert game.draw() is not None, "the game keeps drawing"
        monkeypatch.undo()
        assert hd.water is None and "injected" in hd.stats()["water_error"], "water off, the reason kept"
        ctx.gc()
        assert _gl_counts(ctx) == before, "what it had made is freed"
        game.load(f"{visual.SCENES}/start.json")  # the room's next load tries again
        game.step(3)
        game.draw()
        assert game.window.hd2d_renderer.water is not None and game.window.hd2d_renderer.water_error is None
    finally:
        game.close()


def test_a_puddle_on_a_path_shows(tmp_path: Path) -> None:
    """The path model stands 2 cm above the ground: water must sit above it, not under it (rendering QA)."""
    import json

    import hd2d_visual_study as visual
    import m19_water_study as study

    from engine import project_ops as ops

    project = study.make_project(tmp_path, "onpath", puddle=False, pond=False, rain=False)
    path = project / visual.SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene, wid = ops.place_blank(scene, "start", "OnPath", 640, 224)  # the paths' crossing
    path.write_text(json.dumps(ops.set_water(scene, wid, preset="puddle", width=80, height=48)), encoding="utf-8")
    game = visual.HiddenGame(project, size=visual.SIZE)
    try:
        game.load(f"{visual.SCENES}/start.json")
        game.step(30)
        wet = study.shot(game, (20.0, 6.2, 0.8))
        bodies = game.window.water_bodies
        game.window.water_bodies = []
        dry = study.shot(game, (20.0, 6.2, 0.8))
        game.window.water_bodies = bodies
    finally:
        game.close()
    assert int(study._mask(wet, dry).sum()) > 1500, "the puddle is drawn on the path"
