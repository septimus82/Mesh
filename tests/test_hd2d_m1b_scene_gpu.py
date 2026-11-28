"""M1-B-1: the representative HD-2D crossing, made in Mesh Studio with its own input events and walked in the game with
held arrow keys (hidden windows, ``tooling/hd2d_m1b_scene.py``). Ground at 0 m, a 2 m bridge deck over an open
underpass, stairs between; a guard under the deck where the player stands above it; a cottage you walk into (a door to
a second room, Inside) and back out; the cutaway, camera bounds, and saves on the deck and under it. GL-gated:
MESH_GL_SMOKE=1."""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_m1b_scene

    out = tmp_path_factory.mktemp("m1b")
    # (for its run only, then as they were: absent stays absent, a value comes back, whatever the run did)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        built = hd2d_m1b_scene.build(out, pictures=False)
        checked = hd2d_m1b_scene.check(out, pictures=False, timing=False)
    return {"build": built, "check": checked}


def _leg(run: dict, starts: str) -> dict[str, Any]:
    leg: dict[str, Any] = next(x for x in run["check"]["legs"] if x["after"].startswith(starts))
    return leg


def test_the_crossing_is_built_in_studio(run: dict) -> None:
    built = run["build"]
    assert built["room"]["key"] == "crossing" and built["start_room"].startswith("New games start in Crossing")
    assert built["structures"] == [*(f"platform_4m{s}" for s in ("", "_2", "_3", "_4", "_5", "_6")), "bridge_6m",
                                   "stairs", "stairs_2", "cottage", "lamp_post", "lamp_post_2"]
    assert [(light["x"], light["y"], light["elevation"]) for light in built["lights"]] == [
        (432.0, 160.0, 80.0), (592.0, 160.0, 80.0), (512.0, 640.0, 44.8)]
    assert (built["guard"]["x"], built["guard"]["y"]) == (496.0, 656.0)  # under the deck
    assert built["saved"].startswith("Saved")
    saved = built["saved_crossing"]
    assert saved["structures"] == 12 and saved["camera"]["bounds"] == [0.0, 0.0, 1024.0, 1024.0]
    assert built["crossing_door"]["door_style"] == "passage" and built["inside_door"]["door_style"] == "passage"


def test_the_player_climbs_crosses_the_deck_above_the_guard_and_comes_down(run: dict) -> None:
    assert run["check"]["hd2d_error"] is None
    start = _leg(run, "start")
    assert (start["elevation_m"], start["floor"]) == (0.0, "ground")
    stairs = _leg(run, "half way up the west stairs")
    assert stairs["floor"] == "stairs/col_stairs" and 0.5 < stairs["elevation_m"] < 1.75
    assert (_leg(run, "on the west plateau")["elevation_m"], _leg(run, "on the west plateau")["floor"]) == (
        2.0, "platform_4m_3/col_platform")
    deck = _leg(run, "on the deck")
    assert (deck["elevation_m"], deck["floor"]) == (2.0, "bridge_6m/col_deck")
    guard = deck["guard"]
    assert guard["elevation_m"] == 0.0 and list(guard["stands_on"]) == [0.0, "ground"]
    assert abs(deck["feet_m"][0] - guard["feet_m"][0]) < 0.1 and abs(deck["feet_m"][1] - guard["feet_m"][1]) < 0.15
    assert deck["camera_target"][2] == pytest.approx(2.8, abs=0.05)  # the camera follows the player up
    assert _leg(run, "on the east plateau")["elevation_m"] == 2.0
    down = _leg(run, "down the east stairs")
    assert (down["elevation_m"], down["floor"]) == (0.0, "ground")


def test_the_player_walks_under_the_deck(run: dict) -> None:
    under = _leg(run, "under the deck")
    assert (under["elevation_m"], under["floor"]) == (0.0, "ground")
    assert list(under["overhead"]) == [2.0, "bridge_6m/col_deck"]  # the same x/y, 2 m up
    assert under["camera_target"][2] == pytest.approx(0.8, abs=0.05)


def test_the_cutaway_reveals_the_player_behind_the_cottage_and_inside(run: dict) -> None:
    for starts in ("behind the cottage", "through the doorway"):
        seen = _leg(run, starts)["seen"]
        assert seen["visible_px"] > 0.85 * seen["total_px"], (starts, seen)
        assert seen["without_cutaway_px"] < 0.6 * seen["total_px"], (starts, seen)


def test_the_doorway_goes_in_and_back_out(run: dict) -> None:
    check = run["check"]
    assert (check["door_in"]["from"], check["door_in"]["to"]) == ("crossing.json", "inside.json")
    inside = _leg(run, "through the doorway")
    assert (inside["room"], inside["elevation_m"], inside["floor"]) == ("inside.json", 0.1, "interior/col_floor")
    assert (check["door_out"]["from"], check["door_out"]["to"]) == ("inside.json", "crossing.json")
    back = _leg(run, "back out through the doorway")
    assert (back["room"], back["elevation_m"], back["floor"]) == ("crossing.json", 0.0, "ground")


def test_saves_load_on_the_deck_and_under_it(run: dict) -> None:
    loads = run["check"]["loads"]
    assert set(loads) == {"m1b_deck", "m1b_under"}
    for slot, result in loads.items():
        assert result["ok"] and result["got"] == result["expected"], (slot, result)
    assert loads["m1b_deck"]["got"][1:] == [2.0, "bridge_6m/col_deck"]
    assert loads["m1b_under"]["got"][1:] == [0.0, "ground"]


def test_the_camera_never_shows_past_the_room(run: dict) -> None:
    assert run["check"]["camera_frames"] > 500
    assert run["check"]["camera_bounds_max_drift_m"] < 1e-3
