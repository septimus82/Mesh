"""Milestone 16 Stage 3: the playable floors scene (tooling/hd2d_floors_demo.py) in the real game window. The player,
moved only by held arrow keys through the ordinary controller, climbs the stairs, crosses the bridge, comes down the
other stairs and walks under the same bridge; walls, ledges and railings stop it; saves keep its floor; the warden
finds its way between floors. Hidden window only. GL-gated: set MESH_GL_SMOKE=1."""

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
    # the game's own interaction prompt (not HD-2D) draws with arcade.draw_text, which warns about its speed
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_floors_demo

    project = hd2d_floors_demo.build(tmp_path_factory.mktemp("floors") / "HD-2D floors")
    return hd2d_floors_demo.check(project, tmp_path_factory.mktemp("check"))


def _leg(run: dict, start: str) -> dict:
    return next(leg for leg in run["legs"] if leg["after"].startswith(start))


def test_the_upper_route_climbs_crosses_and_descends(run: dict) -> None:
    assert _leg(run, "start")["floor"] == "ground"
    stairs = _leg(run, "half way up the west stairs")
    assert stairs["floor"] == "crossing/col_stairs_west" and 0.7 < stairs["elevation_m"] < 1.3
    assert _leg(run, "on the west platform")["elevation_m"] == 2.0
    bridge = _leg(run, "mid-bridge")
    assert bridge["floor"] == "crossing/col_bridge_deck" and bridge["elevation_m"] == 2.0
    assert _leg(run, "on the east platform")["floor"] == "crossing/col_platform_east"
    down = _leg(run, "down the east stairs")
    assert down["floor"] == "ground" and down["elevation_m"] == 0.0 and down["feet_m"][1] <= 3.1
    assert {"walk_up", "walk_down", "walk_left", "walk_right"} <= set(run["animation_clips_seen"])


def test_the_lower_route_passes_under_the_same_bridge(run: dict) -> None:
    under = _leg(run, "under the bridge")
    assert under["floor"] == "ground" and under["elevation_m"] == 0.0 and 11 < under["feet_m"][1] < 13
    assert 0 < under["visible_px"] < under["total_px"], "the deck overhead hides part of them"
    assert _leg(run, "north of the bridge")["feet_m"][1] >= 18.0


def test_walls_ledges_and_railings_stop_the_player(run: dict) -> None:
    assert run["blocked"] == {"railing": True, "platform_edge": True, "platform_side": True}
    assert _leg(run, "pushed east off the platform")["elevation_m"] == 2.0, "no falling off"
    assert _leg(run, "under the bridge, pushed east")["feet_m"][0] == pytest.approx(18.7, abs=0.1)


def test_saves_keep_the_floor_on_and_under_the_bridge(run: dict) -> None:
    for slot in ("hd2d_under", "hd2d_bridge"):
        load = run["loads"][slot]
        assert load["ok"] and load["got"] == load["expected"], slot


def test_the_warden_walks_between_floors_by_the_stairs_and_the_camera_follows_smoothly(run: dict) -> None:
    warden = run["warden"]
    assert warden["always_standable"] and warden["elevation_min"] == 0.0 and warden["elevation_max"] == 2.0
    assert warden["trips_down"] >= 1 and warden["trips_up"] >= 1
    camera = run["camera"]
    assert camera["z_min"] == pytest.approx(0.8) and camera["z_max"] == pytest.approx(2.8)
    assert camera["largest_frame_step"] < 0.25, "no jumps while climbing"
