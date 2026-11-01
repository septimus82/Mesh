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
