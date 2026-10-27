"""Milestone 20E: environmental animation in the real renderer and game loop, hidden windows (GL-gated:
MESH_GL_SMOKE=1). The 20D room with 20E's decoration (tooling/m20e_motion_study.py builds it through project_ops):
it moves without a buffer being rebuilt; off, it stands exactly still; a plant turns about its foot (its lowest
pixels never move); a small tree blocks; reloads leave no GPU objects behind."""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
WIND = {"speed": 7.0, "direction": 10.0, "gust": 0.6}


def test_decoration_moves_on_the_gpu_alone_and_stands_still_when_off(tmp_path: Path) -> None:
    import m20e_motion_study as study
    import numpy as np
    from hd2d_demo import _gl_counts

    from engine.hd2d.motion import OFF

    game = study.open_room(tmp_path, "move", decor=True, wind=WIND, motion={"enabled": True})
    try:
        hd = game.window.hd2d_renderer
        layer = hd.scatter
        assert layer is not None and layer.cast_quads  # (the trees' canopies cast)
        a, b = (np.asarray(study.at(game, t, 9.0, 7.0)) for t in (10.0, 10.4))
        assert np.any(a != b, axis=2).mean() > 0.002
        builds, size = dict(layer.builds), layer.memory_bytes()  # (after a first frame: its shadow casters made)
        for _ in range(90):  # the game's own loop: its clock runs, nothing is rebuilt or grows
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
        assert game.window.motion_time > 10.4 + 1.4
        assert layer.builds == builds and layer.memory_bytes() == size
        layer.set_motion(OFF, hd.wind)
        still = [np.asarray(study.at(game, t, 9.0, 7.0)) for t in (10.0, 55.5)]
        assert np.array_equal(still[0], still[1])
        assert game.window.hd2d_world is not None and any(
            w.name == "scatter:tree_small" for w in game.window.hd2d_world.walls)  # (a tree blocks: its trunk)
        ctx, counts = game.window.ctx, []
        for _ in range(3):
            game.load(f"{study.SCENES}/start.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            game.load(f"{study.SCENES}/hills.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            ctx.gc()
            counts.append(_gl_counts(ctx))
        assert counts[1:] == counts[:-1], counts
    finally:
        game.close()


def test_a_plant_turns_about_its_foot(tmp_path: Path) -> None:
    import m20e_motion_study as study
    import numpy as np

    game = study.open_room(tmp_path, "foot", wind={"speed": 12.0, "direction": 0.0, "gust": 0.8},
                           motion={"enabled": True, "sway": 2.0})
    try:
        layer = game.window.hd2d_renderer.scatter
        assert layer is not None
        x, y = 15.0, 4.0  # (open grass by the path)
        layer.set_instances({})
        plain = np.asarray(study.at(game, 3.0, x, y))
        layer.set_instances({"reeds": [(round(x * 32), round(y * 32), 0, 160)]})
        rows = []
        for t in (3.0, 3.3, 3.6, 4.1, 4.7):
            mask = np.any(np.asarray(study.at(game, t, x, y)) != plain, axis=2)
            ys, xs = np.nonzero(mask)
            assert len(ys) > 50
            bottom = ys.max()
            rows.append((bottom, tuple(sorted(xs[ys == bottom])), xs[ys == ys.min()].mean()))
        assert len({(r[0], r[1]) for r in rows}) == 1, rows  # its foot: the same pixels every moment
        assert max(r[2] for r in rows) - min(r[2] for r in rows) > 3  # its top: moving in the wind
    finally:
        game.close()
