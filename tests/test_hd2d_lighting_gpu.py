"""Milestone 16 Stage 4: HD-2D lighting and shadows in the real game window, proven geometric. The GPU's answer to
"how much sun / lamp light reaches this spot" (the scene's own shaders and shadow maps) is compared with rays cast on
the CPU through the crossing's actual triangles, for every spot a character can stand on; then the cases one can
see: a character darker under the bridge, a lamp blocked by the hut, shadows fixed in the world as the camera moves,
the warden walking between light and shade. Frames allocate no GPU objects. Hidden window. Set MESH_GL_SMOKE=1."""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def lit(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_floors_demo
    import hd2d_lighting_demo

    project = hd2d_floors_demo.build(tmp_path_factory.mktemp("lit") / "HD-2D lit")
    return hd2d_lighting_demo.check(project, tmp_path_factory.mktemp("check"))


def test_sun_shadows_agree_with_rays_through_the_geometry_everywhere(lit: dict) -> None:
    sun = lit["geometric_agreement"]["sun"]
    assert sun["disagree"] == 0 and sun["agree"] >= 1000
    assert sun["shaded"] >= 100 and sun["lit"] >= 500, "both shade and sun were tested"
    floors = sun["by_floor"]
    assert floors["ground"]["shaded"] > 0 and floors["col_platform_east"]["shaded"] > 0, "platforms and the hut cast"
    assert floors["col_bridge_deck"]["shaded"] > 0 and floors["col_bridge_deck"]["lit"] > 0, "railings shade the deck"


def test_lamp_shadows_agree_with_rays_and_walls_block_the_light(lit: dict) -> None:
    lamps = lit["geometric_agreement"]["lamps"]
    assert len(lamps) == 2
    for lamp in lamps.values():
        assert lamp["disagree"] == 0 and lamp["agree"] >= 100 and lamp["blocked"] > 0
    behind_on, behind_off = lit["cases"]["hut_lamp_term_behind_hut (on, off)"]
    assert behind_off > 0 and behind_on == 0.0, "the hut stops the blue lamp's light"
    front_on, front_off = lit["cases"]["hut_lamp_term_in_front (on, off)"]
    assert front_on == front_off > 0.1


def test_named_shadows_bridge_platform_and_hut(lit: dict) -> None:
    cases = lit["cases"]
    for name in ("underpass_ground_in_the_deck_shadow (16, 10.8)", "ground_in_west_platform_shadow (6.2, 11)",
                 "east_platform_in_the_hut_shadow (20, 11.5)"):
        on, off = cases[name]
        assert on < 0.6 * off, name
    on, off = cases["open_ground (16, 5)"]
    assert on == off


def test_a_character_is_darker_under_the_bridge_and_only_because_of_it(lit: dict) -> None:
    under, open_, bridge = lit["player_under_bridge"], lit["player_open"], lit["player_on_bridge"]
    assert under["elevation_m"] == 0.0 and bridge["elevation_m"] == 2.0
    assert max(under["light_on"]) < 0.5 * min(under["light_off"]), "the deck shades it"
    assert under["pixels_mean_on"] < 0.5 * under["pixels_mean_off"], "and its drawn pixels are darker"
    for spot in (open_, bridge):
        assert spot["light_on"] == spot["light_off"] and spot["pixels_mean_on"] == spot["pixels_mean_off"]


def test_shadows_stay_put_when_the_camera_moves(lit: dict) -> None:
    for name, views in lit["camera_moves"].items():
        assert views[0]["screen"] != views[1]["screen"], "the camera did move"
        assert views[0]["rgb"] == views[1]["rgb"], name
    shaded = lit["camera_moves"]["shaded (16, 11.4, 0)"][0]["rgb"]
    sunny = lit["camera_moves"]["sunny (16, 7, 0)"][0]["rgb"]
    assert sum(shaded) < 0.5 * sum(sunny)


def test_the_warden_walks_between_light_and_shade(lit: dict) -> None:
    warden = lit["warden"]
    assert warden["light_max"] > 2.5 * warden["light_min"]


def test_frames_allocate_no_gpu_objects_and_lamp_maps_are_drawn_once(tmp_path_factory: pytest.TempPathFactory) -> None:
    import hd2d_demo
    import hd2d_lighting_demo

    project = hd2d_demo.build(tmp_path_factory.mktemp("village") / "village")
    result = hd2d_lighting_demo.bench(project, tmp_path_factory.mktemp("bench"), frames=20)
    for run in result["runs"]:
        assert set(run["gpu_objects_created_during_frames"].values()) == {0}, run["config"]
    by = {run["config"]: run for run in result["runs"]}
    assert by["shadows off, 0 lamps"]["shadow_map_mib"] == 0 and by["shadows on, 2 lamps"]["shadow_map_mib"] == 35
    assert by["shadows on, 8 lamps"]["lamps"] == 8 and by["shadows on, 8 lamps"]["shadow_lamps"] == 2
    assert by["shadows on, 2 lamps"]["shadow_draws"] <= 6, "lamp maps are not re-drawn each frame"
