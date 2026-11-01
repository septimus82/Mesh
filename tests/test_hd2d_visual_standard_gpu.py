"""The HD-2D visual standard (docs/reviews/milestone16_hd2d_visual_direction.md) in the real renderer, in a hidden
window: in a project made from the HD-2D RPG template the gameplay camera never shows past the village's edge, draws
the characters' 32 px per metre at 2x outdoors and 3x indoors (720 lines), and keeps the small interior still while
the player walks about it. GL-gated: set MESH_GL_SMOKE=1."""

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
HERO_PX = 41  # the HD-2D hero's height in its frame, outline included (assets/sprites/hd2d_hero.png)


@pytest.fixture(scope="module")
def spots(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_visual_study as study

    out = tmp_path_factory.mktemp("standard")
    project = study.new_project(out, "project", stage6a=False)
    game = study.HiddenGame(project, size=study.SIZE)
    try:
        game.load(f"{study.SCENES}/start.json")
        game.step(90)
        walk = study.Walk(game, out, "v")
        walk.shot("start")
        walk.go("UP", 1, 15.0)
        walk.shot("centre")
        walk.go("LEFT", 0, 15.0)
        walk.go("UP", 1, 24.0)
        walk.go("RIGHT", 0, 20.0)
        walk.shot("bridge")
        game.load(f"{study.SCENES}/cottage.json")
        game.step(90)
        walk.shot("door")
        walk.go("RIGHT", 0, 8.0)
        walk.go("UP", 1, 6.5)
        walk.shot("east")
        return walk.spots
    finally:
        game.close()


def test_the_camera_never_shows_past_the_village(spots: dict) -> None:
    assert spots["bridge"]["floor"] == "bridge/col_deck" and spots["bridge"]["elevation_m"] == 2.0
    for name in ("start", "centre", "bridge"):  # the south edge, the middle, on the bridge 2 m up by the north
        assert spots[name]["background_pct"] == 0.0, (name, spots[name])
    middle = 360
    assert spots["start"]["player_screen_px"][1] < middle - 40, "at the south edge the player moves off-centre instead"
    assert abs(spots["centre"]["player_screen_px"][1] - spots["bridge"]["player_screen_px"][1]) < 2, \
        "elsewhere the composition holds: the player in the same place on the picture"


def test_characters_are_drawn_at_whole_multiples_of_their_pixels(spots: dict) -> None:
    assert spots["centre"]["player_height_px"] == 2 * HERO_PX and spots["bridge"]["player_height_px"] == 2 * HERO_PX
    # Indoors the camera holds still on the room and looks down steeply, so where the player stands in the room
    # changes their size a little (perspective): within 5% of 3x.
    for name in ("door", "east"):
        assert abs(spots[name]["player_height_px"] - 3 * HERO_PX) <= 0.05 * 3 * HERO_PX, (name, spots[name])


def test_the_interior_stays_still_while_the_player_walks(spots: dict) -> None:
    assert spots["door"]["room"] == "cottage.json" and spots["door"]["feet_m"] != spots["east"]["feet_m"]
    assert spots["door"]["camera_target_m"][:2] == spots["east"]["camera_target_m"][:2]
