"""HD-2D cutaway (settings.hd2d.structures[].cutaway), in the real renderer and a hidden window: in the HD-2D RPG
template, a house marked cutaway no longer hides the player behind or inside it, while what is not marked (the bridge)
keeps hiding the player as it should, nothing is cut where nothing is in the way, and the cut is a small opening, not
the building. Measured in one game, the same frame drawn with and without the cutaway. GL-gated: MESH_GL_SMOKE=1."""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _measure(game: Any, out: Path, name: str) -> dict:
    import hd2d_visual_study as study

    hd = game.window.hd2d_renderer
    player = game.player()
    game.step(45)
    keep = hd._cutaway
    with_cut = game.draw().convert("RGB")
    seen = hd.visible_pixels(player)
    hd._cutaway = set()
    try:
        without = game.draw().convert("RGB")
        hidden = hd.visible_pixels(player)
    finally:
        hd._cutaway = keep
    total = study._total_pixels(hd, player)
    with_cut.save(out / f"{name}_cutaway.png")
    without.save(out / f"{name}_plain.png")
    changed = sum(1 for a, b in zip(with_cut.getdata(), without.getdata()) if a != b)
    return {"visible_with": seen / total, "visible_without": hidden / total, "changed": changed / (1280 * 720),
            "feet": study._feet(player), "floor": getattr(player, "mesh_hd2d_floor", None)}


@pytest.fixture(scope="module")
def spots(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_visual_study as study

    out = tmp_path_factory.mktemp("cutaway")
    project = study.new_project(out, "project", stage6a=False)
    game = study.HiddenGame(project, size=study.SIZE)
    result = {}
    try:
        game.load(f"{study.SCENES}/start.json")
        game.step(90)
        walk = study.Walk(game, out, "c")
        walk.go("UP", 1, 9.5)
        walk.go("LEFT", 0, 11.0)
        result["in_front_of_the_cottage"] = _measure(game, out, "front")
        walk.go("RIGHT", 0, 13.5)
        walk.go("UP", 1, 14.8)
        walk.go("LEFT", 0, 10.0)
        result["behind_the_cottage"] = _measure(game, out, "behind")
        walk.go("RIGHT", 0, 20.0)
        walk.go("UP", 1, 24.0)
        result["under_the_bridge"] = _measure(game, out, "bridge")
        walk.go("DOWN", 1, 5.5)
        walk.go("RIGHT", 0, 29.3)
        walk.go("UP", 1, 12.2)
        result["inside_the_shop"] = _measure(game, out, "shop")
    finally:
        game.close()
    return result


def test_a_house_no_longer_hides_the_player_behind_or_inside_it(spots: dict) -> None:
    for name in ("behind_the_cottage", "inside_the_shop"):
        spot = spots[name]
        assert spot["visible_without"] < 0.5, (name, spot)  # the house really is in the way
        assert spot["visible_with"] > 0.9, (name, spot)
    assert spots["inside_the_shop"]["floor"] == "shop/col_floor"


def test_the_cut_is_an_opening_not_the_building(spots: dict) -> None:
    assert 0 < spots["behind_the_cottage"]["changed"] < 0.03, "a small part of the picture"


def test_what_is_not_marked_or_not_in_the_way_is_untouched(spots: dict) -> None:
    bridge = spots["under_the_bridge"]
    assert bridge["floor"] == "ground" and bridge["visible_with"] == bridge["visible_without"] < 1.0, \
        "the bridge deck still covers the player beneath it"
    assert bridge["changed"] == 0.0
    front = spots["in_front_of_the_cottage"]
    assert front["visible_with"] == front["visible_without"] == 1.0 and front["changed"] == 0.0


# ---- the opening is only where the player is covered (renderer.cutaway_cuts): spots placed by the player's feet in the
#      template village (its cottage at (10, 12) m, its shop at (28, 12) m), at the game camera and the three presets

PLACED = {  # name: (scene variant, feet (m))
    "beside_the_shop": ("start", (25.0, 14.7)),  # north-west of the shop: its roof is near the player, hides nothing
    "beside_the_cottage": ("start", (13.6, 13.0)),  # east of the cottage, level with its roof
    "partly_behind_the_cottage": ("start", (10.0, 16.5)),  # the roof hides the player's legs, not the head
    "behind_the_cottage": ("start", (10.0, 15.0)),
    "inside_the_shop": ("start", (29.3, 12.2)),
    "close_behind_the_cottage": ("start__close", (10.0, 15.0)),
    "wide_behind_the_cottage": ("start__wide", (10.0, 15.0)),
    "indoor_behind_the_cottage": ("start__indoor", (10.0, 15.0)),
}


def _opening_px(hd: Any, player: Any, size: tuple[int, int]) -> tuple[float, float, float, float]:
    """The picture (px, top-left origin) of the opening's box at the player: renderer.cutaway_box's middle and half
    size, across and up the line of sight, through the frame's own view-projection."""
    import math

    from engine.hd2d.renderer import PIXELS_PER_METRE, cutaway_box

    middle, half = cutaway_box(player, hd.elevation_of(player) / PIXELS_PER_METRE, hd.camera.pitch)
    eye, right = hd.camera.eye(), hd.camera.right()
    d = [middle[i] - eye[i] for i in range(3)]
    n = math.sqrt(sum(v * v for v in d))
    d = [v / n for v in d]
    up = (right[1] * d[2] - right[2] * d[1], right[2] * d[0] - right[0] * d[2], right[0] * d[1] - right[1] * d[0])
    vp = hd.last_vp
    xs, ys = [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            p = [middle[i] + right[i] * sx * half[0] + up[i] * sy * half[1] for i in range(3)]
            c = [vp[r][0] * p[0] + vp[r][1] * p[1] + vp[r][2] * p[2] + vp[r][3] for r in range(4)]
            xs.append((c[0] / c[3] + 1) / 2 * size[0])
            ys.append((1 - c[1] / c[3]) / 2 * size[1])
    return min(xs), min(ys), max(xs), max(ys)


@pytest.fixture(scope="module")
def placed(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import json

    import hd2d_visual_study as study
    import numpy as np

    from engine import project_ops as ops

    out = tmp_path_factory.mktemp("cutaway_placed")
    project = study.new_project(out, "project", stage6a=False)
    scenes = project / study.SCENES
    start = json.loads((scenes / "start.json").read_text(encoding="utf-8"))
    for preset in ("close", "wide", "indoor"):
        (scenes / f"start__{preset}.json").write_text(json.dumps(ops.set_hd2d_camera(start, preset=preset)),
                                                      encoding="utf-8")
    game = study.HiddenGame(project, size=study.SIZE)
    result = {}
    try:
        for name, (variant, (fx, fy)) in PLACED.items():
            scene = f"{study.SCENES}/{variant}.json"
            game.load(scene)
            game.step(5)
            player = game.player()
            player.center_x, player.bottom = fx * 32.0, fy * 32.0
            game.step(90)
            assert game.window.scene_controller.current_scene_path.replace("\\", "/").endswith(f"{variant}.json"), name
            hd = game.window.hd2d_renderer
            keep = hd._cutaway
            with_cut = np.asarray(game.draw().convert("RGB")).astype(int)
            seen = hd.visible_pixels(player)
            hd._cutaway = set()
            try:
                without = np.asarray(game.draw().convert("RGB")).astype(int)
                hidden = hd.visible_pixels(player)
            finally:
                hd._cutaway = keep
            total = study._total_pixels(hd, player)
            static = hd.static  # the most any opening can show: the cutaway buildings not drawn at all
            hd.static = [draw for draw in static if id(draw) not in keep]
            try:
                ceiling = hd.visible_pixels(player)
            finally:
                hd.static = static
            changed = np.abs(with_cut - without).max(axis=2) > 0
            x0, y0, x1, y1 = _opening_px(hd, player, study.SIZE)
            ys, xs = np.nonzero(changed)
            outside = int(((xs < x0 - 2) | (xs > x1 + 2) | (ys < y0 - 2) | (ys > y1 + 2)).sum())
            result[name] = {"visible_with": seen / total, "visible_without": hidden / total,
                            "visible_without_the_buildings": ceiling / total, "changed": int(changed.sum()),
                            "outside_opening": outside, "floor": getattr(player, "mesh_hd2d_floor", None)}
    finally:
        game.close()
    return result


def test_a_building_that_hides_nothing_is_not_cut(placed: dict) -> None:
    for name in ("beside_the_shop", "beside_the_cottage"):
        spot = placed[name]
        assert spot["visible_without"] == 1.0, (name, spot)  # (the roof is near the player but covers none of it)
        assert spot["changed"] == 0, (name, spot)


def test_a_covered_player_is_revealed_through_an_opening_its_own_size(placed: dict) -> None:
    covered = [n for n in PLACED if n not in ("beside_the_shop", "beside_the_cottage")]
    for name in covered:
        spot = placed[name]
        assert spot["visible_without"] < 0.9, (name, spot)  # the building really is in the way
        # as much of the player as removing the cutaway buildings altogether would show (what else is in front, a
        # fence, stays in front)
        assert spot["visible_with"] >= spot["visible_without_the_buildings"] - 0.005, (name, spot)
        assert spot["changed"] > 0 and spot["outside_opening"] == 0, (name, spot)  # every cut pixel within the box
    assert 0.0 < placed["partly_behind_the_cottage"]["visible_without"], "partly, not wholly, hidden"
    assert placed["inside_the_shop"]["floor"] == "shop/col_floor"
