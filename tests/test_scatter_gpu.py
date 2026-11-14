"""Milestone 20D: scattered decoration in the real renderer, game loop and Mesh Studio, hidden windows (GL-gated:
MESH_GL_SMOKE=1). The decorated Hills room (tooling/m20d_scatter_study.py builds it through
project_ops.scatter_stroke): it draws in batches; Stage 20A's walks are unchanged by it (decoration is walked
through) and the boulder stops the player; reloads leave no GPU objects behind; Mesh Studio scatters with one undo
step a stroke, cancels safely and says what stands in the way."""

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


def test_the_decorated_room_draws_in_batches_and_leaves_nothing_behind(tmp_path: Path) -> None:
    import hd2d_visual_study as visual
    import m20a_terrain_study as m20a
    import m20d_scatter_study as study
    import numpy as np
    from hd2d_demo import _gl_counts

    game = study.open_room(tmp_path, "draw")
    try:
        hd = game.window.hd2d_renderer
        assert hd.scatter is not None and hd.scatter.count() > 100
        decorated = np.asarray(m20a.shot(game, 9.0, 5.0))
        stats = hd.stats()
        assert 0 < stats["scatter_sprite_draws"] <= len(hd.scatter.sprite_draws), stats
        layer = hd.scatter
        kept = dict(layer.instances)
        layer.set_instances({})  # (none: the same view without it)
        plain = np.asarray(m20a.shot(game, 9.0, 5.0))
        layer.set_instances(kept)
        assert np.any(decorated != plain, axis=2).mean() > 0.005
        ctx, counts = game.window.ctx, []
        for _ in range(4):
            game.load(f"{visual.SCENES}/start.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            game.load(f"{visual.SCENES}/hills.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            ctx.gc()
            counts.append(_gl_counts(ctx))
        assert counts[1:] == counts[:-1] == [counts[1]] * 3, counts
        hd = game.window.hd2d_renderer
        objects = hd.gl_objects()
        assert hd.scatter.prog in objects
        hd.release()
        assert all(getattr(getattr(o, "_glo", None), "value", 0) == 0 for o in objects)
    finally:
        game.close()


def test_decoration_is_walked_through_and_the_boulder_is_not(tmp_path: Path) -> None:
    import m20d_scatter_study as study

    r = study.walks(tmp_path, film=False)  # (the walks, without the report's clips)
    assert r["over_the_hill"]["reached"] == [True] and r["up_the_ramp"]["reached"] == [True], r
    assert r["into_the_cliff"]["reached"] == [False], r
    assert r["along_the_valley_under_the_bridge"]["reached"] == [True], r
    assert r["stairs_and_bridge"]["reached"] == [True, True] and r["into_the_pond"]["reached"] == [True], r
    boulder = r["into_the_boulder"]
    assert boulder["reached"] is False and boulder["stopped_at_m"] < boulder["boulder_m"][0], r


def test_studio_scatters_one_stroke_one_undo_step(tmp_path: Path) -> None:
    import m20d_scatter_study as study

    r = study.studio(tmp_path)
    stroke = r["stroke"]
    assert stroke["undo_steps_added"] == 1 and stroke["shown_equals_saved"] and stroke["instances"] > 50, r
    assert r["undo_gives_none"] and r["redo_gives_it_back"] and r["reopened_same"], r
    for cancel in ("escape", "play_mid_stroke", "room_change_mid_stroke", "refused_upload", "refused_at_release"):
        assert r[cancel]["nothing_recorded"] and r[cancel]["scatter_is_saved"], (cancel, r)
    assert r["focus_lost_mid_stroke"] == {"stroke_ended": True, "undo_steps_added": 1, "no_more_after": True}, r
    t = r["thin_and_remove"]
    assert t["before"] > t["after_ctrl_thin"] > t["after_shift_remove"], r
    assert r["materials_only_earth"]["on"] == ["earth"] and r["materials_only_earth"]["all_on_earth"], r
    assert set(r["out_of_water"]["in_water"]) <= {"reeds", "reeds_cattail"}, r  # (only reeds stand in the shallows)
    assert r["boulder_on_the_player_start"]["warned"], r
    sculpt = r["sculpt_under_scatter"]
    assert sculpt["instances_unmoved"] and sculpt["instances_risen_with_the_ground"] > 0, r
    assert sculpt["their_chunks_rebuilt"], r


def test_grass_alone_makes_nothing_collide_and_a_boulder_does(tmp_path: Path) -> None:
    """Technical QA: one tuft read the boulder's model too, and a room without collision got a world (its walking
    changed). Decoration is walked through; only a boulder makes the room collide."""
    import json

    import hd2d_visual_study as visual
    from hd2d_demo import HiddenGame

    project = visual.new_project(tmp_path, "collide", stage6a=False)
    path = project / visual.SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene["settings"]["hd2d"]["structures"] = []
    worlds = {}
    for name, scatter in (("grass", {"grass_tuft": [[300, 300, 0, 100]]}), ("boulder", {"boulder": [[300, 300, 0, 100]]})):
        scene["settings"]["hd2d"]["scatter"] = scatter
        path.write_text(json.dumps(scene), encoding="utf-8")
        game = HiddenGame(project, size=visual.SIZE)
        try:
            game.load(f"{visual.SCENES}/start.json")
            game.step(2)
            worlds[name] = getattr(game.window, "hd2d_world", None) is not None
        finally:
            game.close()
    assert worlds == {"grass": False, "boulder": True}, worlds
