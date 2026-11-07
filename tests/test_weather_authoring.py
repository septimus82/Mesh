"""Milestone 23C: rain, snow and windborne leaves authored as Studio authors them (``project_ops.set_weather``):
added, sized, shown or hidden and taken away, each one checked edit; the room's own settings and other effects
kept; the engine's four-effect limit; the room's wind moving what is authored."""

from __future__ import annotations

import pytest

from engine import project_ops as ops
from engine.scene_particles import parse_particles
from engine.wind import parse_wind

pytestmark = pytest.mark.fast


def _room() -> dict:
    return {"entities": [], "settings": {}}


def _effects(scene: dict) -> list:
    return list((scene.get("settings") or {}).get("particles") or [])


def test_each_kind_is_added_sized_hidden_shown_and_taken_away() -> None:
    scene = ops.set_weather(_room(), "snow", strength="light")
    scene = ops.set_weather(scene, "wind", strength="steady")
    assert _effects(scene) == [{"preset": "snow", "count": 800}, {"preset": "wind", "count": 400}]
    scene = ops.set_weather(scene, "snow", strength="heavy")
    scene = ops.set_weather(scene, "wind", enabled=False)
    assert _effects(scene) == [{"preset": "snow", "count": 4500}, {"preset": "wind", "count": 400, "enabled": False}]
    states = {s["preset"]: s for s in ops.weather_of(scene)}
    assert states["snow"]["strength"] == "heavy" and states["snow"]["enabled"]
    assert states["wind"]["present"] and not states["wind"]["enabled"] and not states["rain"]["present"]
    assert ops.set_weather(scene, "wind", enabled=True)["settings"]["particles"][1] == {"preset": "wind", "count": 400}
    assert _effects(ops.set_weather(scene, "snow", strength="none")) == [{"preset": "wind", "count": 400,
                                                                        "enabled": False}]
    assert "particles" not in ops.set_weather(ops.set_weather(scene, "snow", strength="none"), "wind",
                                              strength="none")["settings"]


def test_a_rooms_own_settings_and_other_effects_are_kept() -> None:
    custom = {"preset": "snow", "count": 1700, "speed": 1.5, "area": [40, 40, 12], "seed": 9, "opacity": 0.7}
    extra = {"preset": "snow", "count": 300, "seed": 2}
    scene = ops.set_particles(_room(), [custom, {"preset": "rain", "count": 900, "speed": 2.0}, extra])
    state = next(s for s in ops.weather_of(scene) if s["preset"] == "snow")
    assert state["strength"] == "steady" and state["custom"] == ["area", "opacity", "seed", "speed"]
    assert state["extra"] == 1
    scene = ops.set_weather(scene, "snow", strength="light")
    assert _effects(scene)[0] == {**custom, "count": 800} and _effects(scene)[2] == extra  # (only its count)
    scene = ops.set_rain(scene, "heavy")  # (the Sound panel's rain: its own speed kept too, where it was)
    assert _effects(scene)[1] == {"preset": "rain", "count": 6000, "speed": 2.0}


def test_rain_set_from_the_sound_panel_is_shown_again_if_it_was_hidden() -> None:
    scene = ops.set_particles(_room(), [{"preset": "rain", "count": 1200, "enabled": False}])
    assert ops.rain_strength(scene) == "off"
    assert _effects(ops.set_rain(scene, "steady")) == [{"preset": "rain", "count": 3000}]


def test_the_engines_four_effect_limit_and_unknown_choices_are_refused() -> None:
    scene = ops.set_particles(_room(), [{"preset": "rain"}, {"preset": "rain", "seed": 2}, {"preset": "wind"},
                                        {"preset": "wind", "seed": 3}])
    with pytest.raises(ops.OpError, match="at most 4 weather effects"):
        ops.set_weather(scene, "snow", strength="light")
    assert ops.set_weather(scene, "wind", strength="heavy")["settings"]["particles"][2]["count"] == 900  # (edited)
    for preset, change in (("hail", {"strength": "light"}), ("snow", {"strength": "blizzard"}),
                           ("snow", {"enabled": "yes"}), ("snow", {"enabled": False})):
        with pytest.raises(ops.OpError):
            ops.set_weather(_room(), preset, **change)  # (no snow to hide)


def test_what_is_authored_moves_in_the_rooms_wind() -> None:
    scene = ops.set_wind(ops.set_weather(_room(), "wind", strength="light"), speed=5.0, direction=90.0, gust=0.9)
    scene = ops.set_weather(scene, "snow", strength="steady")
    wind = parse_wind(scene["settings"]["wind"])
    for effect in parse_particles(scene["settings"]["particles"], wind):
        assert effect.wind == pytest.approx(wind.vector) and effect.gust == pytest.approx(0.9)
    assert all("wind" not in e and "gust" not in e for e in _effects(scene))  # (no vectors written)
