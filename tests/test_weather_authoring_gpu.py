"""Milestone 23C: weather particles authored in Mesh Studio with its own input events, in hidden windows
(tooling/m23c_weather_studio.py): rain, snow and windborne leaves added, previewed (falling, settling, blown by the
room's wind), hidden, undone and redone, saved, reopened, played and kept to their room; an older room's own
settings reopened and kept. Silent. GL-gated: MESH_GL_SMOKE=1."""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _phase(tmp_path_factory: pytest.TempPathFactory, name: str) -> dict:
    import m23c_weather_studio as study

    out = tmp_path_factory.mktemp(f"m23c_{name}")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        result: dict = study.PHASES[name](out)
        return result
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


@pytest.fixture(scope="module")
def creator(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return _phase(tmp_path_factory, "creator")


def _effects(runtime: dict) -> list:
    return [(preset, count, shown) for preset, count, shown, _wind, _gust in runtime["effects"]]


def test_the_environment_category_opens_the_weather_panel(creator: dict) -> None:
    assert creator["before"]["left_environment_has_button"] and creator["panel_open"] == "weather"
    assert creator["before"]["runtime"]["effects"] == []


def test_rain_and_snow_fall_and_land_in_the_preview(creator: dict) -> None:
    rain, snow = creator["rain"], creator["snow"]
    assert rain["state"]["particles"] == [{"preset": "rain", "count": 3000}]
    assert _effects(rain["runtime"]) == [("rain", 3000, True)] and rain["runtime"]["draw_calls"] == 1
    assert snow["state"]["particles"] == [{"preset": "snow", "count": 4500}]  # (the rain taken away)
    for probed in (rain["probe"], snow["probe"]):
        assert probed["falling"] > 300 and probed["landed"] > 20
        assert probed["landed_within_15cm_of_the_ground"] > probed["landed_sampled"] // 2  # (the rest: on roofs)


def test_windborne_leaves_move_with_the_rooms_gusty_breeze(creator: dict) -> None:
    leaves = creator["leaves"]
    assert leaves["state"]["wind"] == {"speed": 5.0, "direction": 90.0, "gust": 0.9}  # (Gusty, To North)
    for _preset, _count, _shown, wind, gust in leaves["runtime"]["effects"]:
        assert wind == pytest.approx([0.0, 5.0], abs=1e-3) and gust == 0.9  # (no vector of their own)
    east, north = creator["snow_hidden"]["leaves_drift"]["median_m_s"]
    assert creator["snow_hidden"]["leaves_drift"]["matched"] > 50 and north > 2.0 and abs(east) < 1.0


def test_one_effect_hidden_while_the_other_shows(creator: dict) -> None:
    hidden = creator["snow_hidden"]
    assert _effects(hidden["runtime"]) == [("snow", 4500, False), ("wind", 900, True)]
    assert hidden["runtime"]["draw_calls"] == 1 and hidden["state"]["particles"][0]["enabled"] is False


def test_undo_and_redo_a_weather_change(creator: dict) -> None:
    steps = creator["undo_redo"]
    assert steps["undone"] == steps["before"] and steps["redone"] == steps["changed"] != steps["before"]
    assert ("snow", 800, True) in _effects(steps["runtime_after_redo"])


def test_indoors_keeps_its_precipitation_rule(creator: dict) -> None:
    indoors = creator["indoors"]
    assert indoors["state"]["exposure"] == "indoor" and _effects(indoors["runtime"]) == [("wind", 900, True)]
    assert "indoors" in indoors["runtime"]["notice"]


def test_saved_reopened_and_played_as_configured_and_kept_to_its_room(creator: dict) -> None:
    assert creator["saved_message"].startswith("Saved") and creator["configured"] == creator["in_the_saved_file"]
    reopened = creator["reopened"]
    assert reopened["state"] == creator["in_the_saved_file"] and reopened["unsaved"] == []
    configured = _effects(creator["configured_runtime"])
    assert configured == [("snow", 800, True), ("wind", 900, True)] == _effects(reopened["runtime"])
    for cycle in creator["play_stop"]:
        assert cycle["mode"] == "play" and _effects(cycle["runtime"]) == configured and cycle["runtime"]["draw_calls"] == 2
        assert cycle["master_volume"] == 0.0 and cycle["after_stop"]["mode"] == "edit"
    assert creator["other_room"]["runtime"]["effects"] == [] and creator["other_room"]["particles"] is None
    assert _effects(creator["back"]) == configured
    assert creator["in_the_saved_file"]["sounds"]["rain"] == "" == creator["in_the_saved_file"]["sounds"]["wind"]


def test_an_older_rooms_own_weather_is_reopened_and_kept(tmp_path_factory: pytest.TempPathFactory) -> None:
    report = _phase(tmp_path_factory, "compat")
    assert report["reopened_unchanged"] and report["unsaved_on_open"] == []
    assert report["only_snow_count_changed"], report["after_snow_heavy"]
    assert report["rain_light_kept_hidden"] == {"preset": "rain", "count": 1200, "enabled": False}
    assert any(line.startswith("Kept as set") for line in report["panel_says"])
