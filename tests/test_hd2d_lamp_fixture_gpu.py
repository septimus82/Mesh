"""#458: a lamp lit at its lamp post's lantern lights the ground round it, in the real game (hidden window), while
walls still block it, however close to the light; the GPU's light (Lighting.probe, the scene's own shaders and shadow
maps) agrees with rays cast on the CPU through the room's triangles (tooling/hd2d_lighting_demo.fixture_check). The
lamps are the starter kit's lamp posts in a project made from the HD-2D RPG template. Set MESH_GL_SMOKE=1."""

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
def room(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_lighting_demo

    from engine.project_scaffold import create_project

    project = tmp_path_factory.mktemp("lamps") / "Lamp fixtures"
    create_project(project, "Lamp fixtures", "hd2d_rpg")
    return dict(hd2d_lighting_demo.fixture_check(project))


def test_each_lamps_fixture_is_its_own_lamp_post_and_never_a_wall(room: dict) -> None:
    assert room["fixtures"] == {"lamp_a": ["lamp_a"], "lamp_b": ["lamp_b"]}


def test_a_lamp_in_its_lantern_lights_the_ground_round_it(room: dict) -> None:
    # With shadows on, exactly what it gives with shadows off: its own lantern no longer blocks it (#458: it gave 0)
    for name in ("a_open_1m", "a_open_2m", "a_open_3m", "a_side_2m", "b_open_2m", "b_before_far_wall"):
        sample = room["named"][name]
        assert sample["off"] > 0.05 and sample["on"] == pytest.approx(sample["off"], abs=1e-3), (name, sample)
        assert sample["cpu"] is True, (name, sample)


def test_a_wall_a_quarter_metre_from_the_light_still_blocks_it(room: dict) -> None:
    # The wall's face is 0.25 m from lamp A's light: well inside 0.35 m, and still a shadow behind it
    for name in ("a_behind_near_wall_1.5m", "a_behind_near_wall_2.5m", "a_behind_near_wall_skew",
                 "a_behind_near_wall_4m"):
        sample = room["named"][name]
        assert sample["off"] > 0.02 and sample["on"] == 0.0, (name, sample)
        assert sample["cpu"] is False, (name, sample)


def test_an_occluder_wholly_within_0_35_m_of_the_light_still_blocks_it(room: dict) -> None:
    # A panel 0.23-0.33 m from the light (both faces): a clearance round the lamp would erase it; it still casts
    for name in ("a_behind_panel_3.5m", "a_behind_panel_4m", "a_behind_panel_skew"):
        sample = room["named"][name]
        assert sample["off"] > 0.02 and sample["on"] == 0.0, (name, sample)
        assert sample["cpu"] is False, (name, sample)


def test_a_farther_wall_still_blocks_and_lights_what_is_in_front(room: dict) -> None:
    for name in ("b_behind_far_wall_1.5m", "b_behind_far_wall_2.5m"):
        sample = room["named"][name]
        assert sample["off"] > 0.0 and sample["on"] == 0.0 and sample["cpu"] is False, (name, sample)


def test_gpu_and_cpu_agree_round_both_lamps(room: dict) -> None:
    agreement = room["agreement"]
    assert agreement["disagree"] == 0, agreement["mismatches"]
    assert agreement["agree"] >= 400 and agreement["reached"] >= 300 and agreement["blocked"] >= 80, agreement


def test_the_lamps_maps_are_drawn_once(room: dict) -> None:
    assert room["shadow_lamps"] == 2 and room["lamp_map_renders"] == 1
    assert room["lamp_map_renders_after_3_frames"] == 1
