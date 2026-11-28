"""Milestone 21C2: an indoor room that asks to hear the weather outside hears its own rain and wind settings, quietly.

Headless, as tests/test_sound_emitters.py: a stand-in window and the audio manager on a stand-in backend that counts
every player made and released. A room's settings are given as the scene loader gives them; the particle layer on
screen is given apart (an indoor room's has no rain: ``engine.scene_particles.configure`` leaves it out). Nothing is
played aloud. The real-window check is tests/test_indoor_weather_gpu.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.audio as audio_mod
import engine.project_ops as ops
from engine import sound_emitters as se
from engine.scene_particles import parse_particles
from tests.test_audio_buses_and_scene_music import Backend
from tests.test_sound_emitters import RAIN, WIND, _run, _sprite, _window

pytestmark = pytest.mark.fast

RAIN_KEY, WIND_KEY = "weather:rain", "weather:wind"
STEADY = [{"preset": "rain"}]  # the rain preset as it is: 3,000 drops, the rate ``rain_rate`` calls 1.0
SOUNDS = {"rain": RAIN, "wind": WIND, "rain_volume": 0.6, "wind_volume": 0.5}
GALE = {"speed": 14.0, "gust": 0.0}  # steady, at the speed the wind's sound is at full strength
OUTSIDE = {"particles": STEADY, "wind": GALE, "weather_sounds": SOUNDS}
INSIDE = {**OUTSIDE, "weather_exposure": "indoor"}  # the same weather set, in an indoor room (not yet heard)
HEARD = {**INSIDE, "weather_sounds": {**SOUNDS, "indoors": True}}


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Backend:
    return _backend(monkeypatch)


def _backend(monkeypatch: pytest.MonkeyPatch, missing: tuple[str, ...] = ()) -> Backend:
    fake = Backend(missing)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "stop_sound", fake.stop)
    monkeypatch.setattr(audio_mod, "resolve_path", lambda p: p)
    return fake


def _layer(settings: dict[str, Any]) -> Any:
    """The particles on screen in a room with these settings: an indoor room's rain and snow are left out."""
    effects = parse_particles(settings.get("particles"))
    if settings.get("weather_exposure") == "indoor":
        effects = tuple(e for e in effects if e.preset not in ("rain", "snow"))
    return effects or None


def _room(settings: dict[str, Any], window: Any = None, name: str = "room") -> Any:
    """A room with these settings, entered: a new game window, or the one given walking into it."""
    if window is None:
        return _window(_sprite(0, 0), settings, _layer(settings))
    effects = _layer(settings)
    window.scene_particles = None if effects is None else type(window)(effects=effects, enabled=[True] * len(effects))
    se.reset(window, name, settings)
    return window


def _level(window: Any, key: str) -> float:
    track = window.audio._loops.get(key)
    return track.volume if track is not None else 0.0


def _settled(settings: dict[str, Any]) -> tuple[float, float]:
    window = _room(settings)
    _run(window, 8.0)
    return round(_level(window, RAIN_KEY), 4), round(_level(window, WIND_KEY), 4)


# ---------------------------------------------------------------- the setting
def test_the_setting_is_off_unless_set_and_checked_with_a_reason() -> None:
    assert se.parse_weather_sounds({"rain": RAIN}).indoors is False  # a room made before Milestone 21C2
    assert se.parse_weather_sounds({"rain": RAIN, "indoors": True}).indoors is True
    assert se.parse_weather_sounds({"indoors": True}) == se.WeatherSounds(indoors=True)  # set before any sound is chosen
    with pytest.raises(se.EmitterError, match="indoors must be true or false"):
        se.parse_weather_sounds({"rain": RAIN, "indoors": "quietly"})
    with pytest.raises(se.EmitterError, match="unknown setting"):
        se.parse_weather_sounds({"rain": RAIN, "muffled": True})


# ---------------------------------------------------------------- outdoors, and indoors as it was
def test_outdoors_the_weather_is_heard_as_before_whatever_the_setting(backend: Backend) -> None:
    plain = _settled(OUTSIDE)
    assert plain == pytest.approx((0.6, 0.5), abs=0.01)  # steady rain and a gale, at their own volumes
    assert _settled({**OUTSIDE, "weather_sounds": {**SOUNDS, "indoors": True}}) == plain  # the setting does nothing outdoors


def test_an_indoor_room_without_the_setting_is_as_it_was(backend: Backend) -> None:
    window = _room(INSIDE)
    _run(window, 8.0)
    assert RAIN_KEY not in window.audio._loops and RAIN not in backend.loads  # no rain heard: nothing even opened
    assert _level(window, WIND_KEY) == pytest.approx(0.5, abs=0.01)  # its wind as outdoors: unchanged by this milestone
    assert window.soundscape.diagnostics()["weather_from_outside"] is False


# ---------------------------------------------------------------- indoors, hearing the weather outside
def test_an_indoor_room_that_asks_hears_its_own_rain_and_wind_quietly(backend: Backend) -> None:
    window = _room(HEARD)
    assert window.scene_particles is None  # no rain on screen in here
    _run(window, 8.0)
    assert _level(window, RAIN_KEY) == pytest.approx(0.6 * se.INDOORS, abs=0.005)
    assert _level(window, WIND_KEY) == pytest.approx(0.5 * se.INDOORS, abs=0.005)
    assert window.soundscape.diagnostics()["weather_from_outside"] is True
    assert sorted(p.path for p in backend.live()) == [RAIN, WIND]  # the same two loops as outdoors: no more players


def test_how_hard_the_rain_set_falls_is_how_loud_it_is_heard(backend: Backend) -> None:
    def heard(particles: Any) -> float:
        return _settled({**HEARD, "particles": particles})[0]

    steady = heard(STEADY)
    assert heard([{"preset": "rain", "count": 1200}]) == pytest.approx(steady * 0.4, abs=0.005)  # light: 1,200 of 3,000
    assert heard([{"preset": "rain", "count": 6000}]) == pytest.approx(steady, abs=0.005)  # heavy: as loud as it gets
    assert heard([{"preset": "snow"}, {"preset": "rain", "count": 1200}]) == pytest.approx(steady * 0.4, abs=0.005)


def test_no_rain_is_invented_where_none_is_set(backend: Backend) -> None:
    for particles in (None, [], [{"preset": "snow"}], [{"preset": "rain", "enabled": False}]):
        window = _room({**HEARD, "particles": particles, "wind": None})
        _run(window, 4.0)
        assert window.audio.loops() == {}, particles  # a rain sound chosen, and no rain set: silence
    assert backend.players == []


def test_a_calm_room_has_no_wind_outside_and_a_room_with_no_sound_has_nothing_to_play(backend: Backend) -> None:
    assert _settled({**HEARD, "wind": None}) == pytest.approx((0.6 * se.INDOORS, 0.0), abs=0.005)
    assert _settled({**HEARD, "weather_sounds": {"indoors": True}}) == (0.0, 0.0)
    assert sorted({p.path for p in backend.players}) == [RAIN]


def test_particles_the_game_cant_use_mean_no_rain_from_outside_and_nothing_raised(backend: Backend) -> None:
    window = _room(HEARD)  # a room whose rain is heard from outside ...
    _run(window, 6.0)
    assert _level(window, RAIN_KEY) > 0.1
    se.reset(window, "broken", {**HEARD, "particles": [{"preset": "hail"}]})  # ... then one whose particles are no use
    _run(window, 12.0)
    assert RAIN_KEY not in window.audio._loops and window.soundscape.outside_rain == 0.0  # the last room's is not kept
    assert _level(window, WIND_KEY) == pytest.approx(0.5 * se.INDOORS, abs=0.01)  # its wind is still the wind outside


# ---------------------------------------------------------------- walking in and out
def test_walking_in_the_rain_carries_on_and_eases_down_and_up_again_on_the_way_out(backend: Backend) -> None:
    window = _room(OUTSIDE)
    _run(window, 8.0)
    heard = {RAIN_KEY: [_level(window, RAIN_KEY)], WIND_KEY: [_level(window, WIND_KEY)]}

    def stay(seconds: float) -> None:
        for _ in range(round(seconds * 60)):
            _run(window, 1 / 60)
            for key in heard:
                heard[key].append(_level(window, key))

    _room(HEARD, window, "cottage")  # through the door
    stay(8.0)
    indoors = (heard[RAIN_KEY][-1], heard[WIND_KEY][-1])
    assert indoors == pytest.approx((0.6 * se.INDOORS, 0.5 * se.INDOORS), abs=0.005)
    _room(OUTSIDE, window, "village")  # and out again
    stay(8.0)
    assert (heard[RAIN_KEY][-1], heard[WIND_KEY][-1]) == pytest.approx((0.6, 0.5), abs=0.01)
    for key, levels in heard.items():
        assert max(abs(a - b) for a, b in zip(levels, levels[1:])) < 0.01, f"{key}: no jump in or out"
        assert min(levels) > 0.1, f"{key}: never cut"
    assert sorted(p.path for p in backend.players) == [RAIN, WIND]  # the same two players throughout: none restarted
    assert all(not p.released for p in backend.players)


def test_the_last_rooms_rain_does_not_follow_into_a_room_with_none_set(backend: Backend) -> None:
    window = _room(OUTSIDE)
    _run(window, 4.0)
    assert _level(window, RAIN_KEY) > 0.5
    _room({**HEARD, "particles": None, "wind": None}, window, "cellar")  # asks to hear outside; has no weather set
    _run(window, 12.0)  # (the weather fades over several seconds, as it does when it stops outdoors)
    assert window.audio.loops() == {} and backend.live() == []  # the village's rain faded out and was released


def test_loading_a_save_straight_into_the_room_sounds_as_walking_into_it_does(backend: Backend) -> None:
    walked = _room(OUTSIDE)
    _run(walked, 6.0)
    _room(HEARD, walked, "cottage")
    _run(walked, 15.0)
    loaded = _room(HEARD)  # a new game window, this room first
    _run(loaded, 15.0)
    for key in (RAIN_KEY, WIND_KEY):
        # (within twice RESEND: a loop is given a new volume only once it differs by that much, from either side)
        assert _level(loaded, key) == pytest.approx(_level(walked, key), abs=2 * se.RESEND + 0.001)
    assert _level(loaded, RAIN_KEY) == pytest.approx(0.6 * se.INDOORS, abs=0.005)


def test_turning_the_setting_off_again_is_the_room_as_it_was(backend: Backend) -> None:
    window = _room(HEARD)
    _run(window, 6.0)
    assert _level(window, RAIN_KEY) > 0.1
    _room(INSIDE, window)  # the creator turned it off: the room loaded again
    _run(window, 6.0)
    assert RAIN_KEY not in window.audio._loops
    assert _level(window, WIND_KEY) == pytest.approx(0.5, abs=0.01)
    assert [p.path for p in backend.live()] == [WIND]  # the rain's player released


def test_rain_or_wind_taken_out_of_the_room_stops_being_heard(backend: Backend) -> None:
    window = _room(HEARD)
    _run(window, 6.0)
    _room({**HEARD, "particles": None}, window)  # Rain: Off in Studio (the room loads again)
    _run(window, 6.0)
    assert RAIN_KEY not in window.audio._loops and _level(window, WIND_KEY) == pytest.approx(0.5 * se.INDOORS, abs=0.005)
    _room({**HEARD, "particles": None, "wind": None}, window)  # Wind: Calm
    _run(window, 6.0)
    assert window.audio.loops() == {} and backend.live() == []


def test_going_in_and_out_and_playing_and_stopping_leave_no_player_behind(backend: Backend) -> None:
    window = _room(OUTSIDE)
    for _ in range(6):
        _run(window, 0.4)
        _room(HEARD, window, "cottage")
        _run(window, 0.4)
        _room(OUTSIDE, window, "village")
    _run(window, 1.0)
    assert sorted(p.path for p in backend.live()) == [RAIN, WIND] and len(backend.players) == 2
    for _ in range(4):  # a play-test of the indoor room, started and stopped
        se.reset(window, "", {})
        window.scene_particles = None
        _run(window, 3.0)
        assert backend.live() == []
        _room(HEARD, window, "cottage")
        _run(window, 1.0)
        assert len(backend.live()) == 2
    window.audio.shutdown()
    assert backend.live() == []


def test_a_weather_sound_that_cant_be_played_is_silent_and_harmless(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = _backend(monkeypatch, missing=(RAIN,))
    window = _room(HEARD)
    _run(window, 3.0)
    assert RAIN_KEY not in window.audio._loops and [p.path for p in broken.live()] == [WIND]


def test_the_ambience_volume_and_muting_apply_as_ever(backend: Backend) -> None:
    window = _room(HEARD)
    _run(window, 8.0)
    rain = next(p for p in backend.live() if p.path == RAIN)
    assert rain.volume == pytest.approx(0.6 * se.INDOORS, abs=0.005)
    window.audio.set_ambience_volume(0.5)
    assert rain.volume == pytest.approx(0.3 * se.INDOORS, abs=0.005)
    window.audio.set_muted(True)
    _run(window, 0.5)
    assert rain.volume == 0.0
    window.audio.set_muted(False)
    _run(window, 0.5)
    assert rain.volume == pytest.approx(0.3 * se.INDOORS, abs=0.005) and len(backend.players) == 2


# ---------------------------------------------------------------- authoring: the op, what Studio says, AI tools
def _scene(**settings: Any) -> dict[str, Any]:
    return {"name": "Room", "settings": dict(settings), "entities": []}


def test_the_op_sets_it_and_off_is_no_setting_at_all() -> None:
    scene = ops.set_weather_sounds(_scene(), rain=RAIN)
    assert ops.weather_sounds_of(scene)["indoors"] is False and "indoors" not in scene["settings"]["weather_sounds"]
    on = ops.set_weather_sounds(scene, indoors=True)
    assert on["settings"]["weather_sounds"] == {"rain": RAIN, "indoors": True} and ops.weather_sounds_of(on)["indoors"]
    assert ops.set_weather_sounds(on, indoors=False) == scene  # the room as it was before it was ever set
    alone = ops.set_weather_sounds(_scene(), indoors=True)  # turned on before a sound is chosen: kept
    assert alone["settings"]["weather_sounds"] == {"indoors": True}
    assert "weather_sounds" not in ops.set_weather_sounds(alone, indoors=False)["settings"]
    assert ops.set_weather_sounds(on, rain="")["settings"]["weather_sounds"] == {"rain": "", "indoors": True}
    with pytest.raises(ops.OpError, match="indoors must be true or false"):
        ops.set_weather_sounds(scene, indoors="yes")


def test_studio_is_told_what_is_heard_or_why_nothing_is() -> None:
    outdoors = ops.indoor_weather(ops.set_weather_sounds(_scene(particles=STEADY), rain=RAIN, indoors=True))
    assert outdoors["indoor"] is False and (outdoors["rain"], outdoors["wind"]) == (False, False)
    assert outdoors["message"].startswith("Outdoors")

    room = ops.set_weather_exposure(_scene(), "indoor")
    off = ops.indoor_weather(room)
    assert off["indoor"] and not off["enabled"] and "Turn on Hear outside weather indoors" in off["message"]

    on = ops.set_weather_sounds(room, indoors=True)
    nothing = ops.indoor_weather(on)
    assert nothing["enabled"] and not (nothing["rain"] or nothing["wind"])
    assert nothing["message"] == ("Nothing will be heard from outside yet: this room has no rain or wind set, so there "
                                  "is no weather outside to hear.")

    rained = ops.set_rain(on, "steady")  # rain set, no sound chosen for it
    assert ops.indoor_weather(rained)["message"] == "Nothing will be heard from outside yet: the rain has no sound chosen."

    both = ops.set_weather_sounds(ops.set_wind(rained, speed=3.0, gust=0.3), rain=RAIN, wind=WIND)
    heard = ops.indoor_weather(both)
    assert (heard["rain"], heard["wind"]) == (True, True)
    assert heard["message"] == "Indoors: the rain and wind set here are heard quietly, as the weather outside."

    part = ops.indoor_weather(ops.set_weather_sounds(both, wind=""))
    assert (part["rain"], part["wind"]) == (True, False)
    assert part["message"] == ("Indoors: the rain set here is heard quietly, as the weather outside. Not heard: the wind "
                               "has no sound chosen.")

    as_it_was = ops.indoor_weather(ops.set_weather_sounds(both, indoors=False))  # an indoor room with a wind, before this
    assert "The wind set here is heard at full strength, as outdoors." in as_it_was["message"]


def test_an_ai_tool_sets_it_and_it_is_undone_redone_saved_and_read_back(tmp_path: Path) -> None:
    from engine import authoring

    assert "set_weather_sounds" in authoring.operations() and "indoor_weather" not in authoring.operations()  # (it only reads)
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="blank")
    world = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    project = Project(root, world)
    authoring.apply(project, [{"op": "set_weather_exposure", "exposure": "indoor"},
                              {"op": "set_rain", "strength": "steady"},
                              {"op": "set_weather_sounds", "rain": RAIN, "indoors": True}])

    def setting() -> Any:
        return (project.scene()["settings"].get("weather_sounds") or {}).get("indoors")

    assert setting() is True and ops.indoor_weather(project.scene())["rain"] is True
    project.edit_scene(lambda room: ops.set_weather_sounds(room, indoors=False))  # the person turns it off
    assert setting() is None
    project.undo()
    assert setting() is True
    project.redo()
    assert setting() is None
    project.undo()
    project.save()
    reopened = Project(root, world)
    assert reopened.scene()["settings"]["weather_sounds"] == {"rain": RAIN, "indoors": True}
    assert reopened.scene()["settings"]["weather_exposure"] == "indoor"
    with pytest.raises(authoring.ChangeError, match="true or false"):
        authoring.apply(reopened, [{"op": "set_weather_sounds", "indoors": "yes"}])


def test_the_scene_loader_and_the_export_take_a_room_with_it(tmp_path: Path) -> None:
    from engine.scene_loader import SceneLoader
    from engine.tooling.asset_manifest import _extract_refs_from_scene

    scene = ops.set_weather_sounds(ops.set_rain(ops.set_weather_exposure(_scene(), "indoor"), "steady"),
                                   rain=RAIN, wind=WIND, indoors=True)
    path = tmp_path / "room.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    loaded = SceneLoader().load_scene(str(path))
    assert loaded["settings"]["weather_sounds"]["indoors"] is True and loaded["settings"]["weather_exposure"] == "indoor"
    refs = {r.asset_id: r.field_path for r in _extract_refs_from_scene(scene, "room.json")}
    assert refs == {RAIN: "settings.weather_sounds.rain", WIND: "settings.weather_sounds.wind"}
