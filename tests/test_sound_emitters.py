"""Milestone 21B: sound emitters heard from where the player is, the weather heard, and their players.

Headless: a stand-in window (its player, its particle layer) and the audio manager on a stand-in backend that counts
every player made and released; nothing is played aloud (the real-backend check is ``tooling/audio_smoke.py``)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import engine.audio as audio_mod
from engine import sound_emitters as se
from engine.audio import AudioManager
from engine.scene_particles import parse_particles
from tests.test_audio_buses_and_scene_music import Backend

pytestmark = pytest.mark.fast

WATER, BIRDS, RAIN, WIND = (f"assets/ambience/{n}_loop.wav" for n in ("stream", "birds", "rain", "wind"))


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Backend:
    fake = Backend()
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "stop_sound", fake.stop)
    monkeypatch.setattr(audio_mod, "resolve_path", lambda p: p)
    return fake


def _sprite(x: float, y: float, z: float = 0.0, eid: str = "") -> Any:
    return SimpleNamespace(center_x=x, center_y=y, mesh_entity_data={"id": eid, "elevation": z}, sprite_lists=[1])


def _window(player: Any, settings: dict[str, Any] | None = None, effects: Any = None) -> Any:
    window = SimpleNamespace(audio=AudioManager(), hd2d_renderer=None,
                             scene_controller=SimpleNamespace(_find_player_sprite=lambda: player),
                             scene_particles=None if effects is None else SimpleNamespace(
                                 effects=effects, enabled=[True] * len(effects)))
    se.reset(window, "room", settings or {})
    return window


def _emit(window: Any, eid: str, x: float, y: float, z: float = 0.0, **cfg: Any) -> Any:
    sprite = _sprite(x, y, z, eid)
    se.soundscape_of(window).register(sprite, se.parse_emitter({"sound": WATER, **cfg}))
    return sprite


def _run(window: Any, seconds: float, step: float = 1 / 60) -> None:
    for _ in range(round(seconds / step)):
        window.audio.update(step)
        se.update(window, step)


# ---------------------------------------------------------------- settings and the distance curve
def test_an_emitters_settings_are_checked_with_reasons() -> None:
    e = se.parse_emitter({"sound": WATER, "radius": 32, "distance": 400})
    assert (e.volume, e.stereo, e.loop, e.enabled) == (0.8, True, True, True)
    for bad, reason in (({"sound": 5}, "file path"), ({"sound": "a.txt"}, ".wav, .ogg or .mp3"),
                        ({"volume": 2}, "volume must be a number from 0 to 1"),
                        ({"radius": 500, "distance": 400}, "must be less than"),
                        ({"stereo": "yes"}, "true or false"), ({"echo": 1}, "unknown setting")):
        with pytest.raises(se.EmitterError, match=reason):
            se.parse_emitter(bad)


def test_full_strength_inside_its_radius_fading_smoothly_to_silence_at_its_distance() -> None:
    e = se.parse_emitter({"sound": WATER, "radius": 64, "distance": 320})
    samples = [se.gain(d, e) for d in range(0, 400, 8)]
    assert samples[:9] == [1.0] * 9 and samples[-10:] == [0.0] * 10
    assert all(a >= b for a, b in zip(samples, samples[1:]))  # never louder further away
    steps = [a - b for a, b in zip(samples, samples[1:])]
    assert max(steps) < 0.07  # no sudden drop: 8 px steps change it by under 7 %
    assert se.gain(192, e) == pytest.approx(0.5)  # half-way: half strength (a smoothstep is symmetric)


def test_stereo_pans_by_its_side_less_when_close_and_never_hard() -> None:
    e = se.parse_emitter({"sound": WATER, "radius": 64, "distance": 320})
    assert se.pan(200, 200, e) == pytest.approx(se.STEREO_WIDTH)  # straight to the right
    assert se.pan(-200, 200, e) == pytest.approx(-se.STEREO_WIDTH)
    assert se.pan(0, 200, e) == 0.0  # ahead or behind: centred
    assert abs(se.pan(16, 16, e)) < 0.25 * se.STEREO_WIDTH + 1e-9  # inside its radius: hardly to one side
    assert se.pan(200, 200, se.parse_emitter({"sound": WATER, "stereo": False})) == 0.0


# ---------------------------------------------------------------- following the listener
def test_walking_toward_a_stream_and_away_it_rises_and_falls_without_restarting(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    _emit(window, "stream", 600, 0, radius=64, distance=400, fade_in=0.0)
    levels = []
    for x in range(0, 1200, 20):  # past it and away again
        player.center_x = x
        _run(window, 0.1)
        levels.append(window.audio._loops["emitter:room:stream"].volume if "emitter:room:stream" in window.audio._loops
                      else 0.0)
    peak = levels.index(max(levels))
    assert levels[0] == 0.0 and levels[-1] == 0.0 and max(levels) == pytest.approx(0.8, abs=0.01)
    assert all(a <= b + 1e-6 for a, b in zip(levels[:peak], levels[1:peak + 1]))  # rising on the way in
    assert all(a + 1e-6 >= b for a, b in zip(levels[peak:], levels[peak + 1:]))  # falling on the way out
    assert len(backend.players) == 1  # one player, in reach once: never restarted on the way past


def test_out_of_reach_nothing_plays_or_decodes(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    for i in range(30):
        _emit(window, f"far{i}", 2000 + 40 * i, 0)
    _run(window, 1.0)
    assert backend.loads == [] and backend.players == []


def test_heights_count_in_an_hd2d_room(backend: Backend) -> None:
    window = _window(_sprite(0, 0, z=0.0))
    _emit(window, "hilltop", 0, 0, z=300.0, radius=32, distance=320, fade_in=0.0)
    _run(window, 0.5)
    level = window.audio._loops["emitter:room:hilltop"].volume
    assert level == pytest.approx(0.8 * se.gain(300.0, se.parse_emitter({"sound": WATER, "radius": 32, "distance": 320})),
                                  abs=0.01)
    assert level < 0.1  # 9 m above: barely heard, though straight overhead


def test_a_crowd_of_emitters_plays_only_the_loudest_and_few_copies_of_one_sound(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    for i in range(40):  # dozens about the player, half of one sound
        sound = WATER if i % 2 else BIRDS
        sprite = _sprite(30 * (i % 8), 30 * (i // 8), eid=f"e{i}")
        se.soundscape_of(window).register(sprite, se.parse_emitter({"sound": sound, "distance": 600}))
    _run(window, 0.5)
    live = backend.live()
    assert len(live) <= se.MAX_ACTIVE
    assert sum(p.path == WATER for p in live) <= se.MAX_SAME_SOUND and sum(p.path == BIRDS for p in live) <= se.MAX_SAME_SOUND
    _run(window, 3.0)  # (levels and the shared headroom settle)
    calls = se.soundscape_of(window).loop_calls
    _run(window, 1.0)  # standing still: frames stop calling the audio manager
    assert se.soundscape_of(window).loop_calls - calls < 10


def test_leaving_the_room_stops_its_emitters_and_coming_back_resumes_them(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    _emit(window, "stream", 50, 0, fade_in=0.0)
    _run(window, 0.3)
    assert len(backend.live()) == 1
    se.reset(window, "other", {})  # into a room without it
    _run(window, 2.0)
    assert backend.live() == []
    se.reset(window, "room", {})  # back: its emitter registers again (the same key)
    _emit(window, "stream", 50, 0, fade_in=0.0)
    _run(window, 0.3)
    assert len(backend.live()) == 1 and len(window.audio.loops()) == 1


def test_disabled_and_soundless_emitters_are_silent(backend: Backend) -> None:
    window = _window(_sprite(0, 0))
    _emit(window, "off", 10, 0, enabled=False)
    se.soundscape_of(window).register(_sprite(10, 0, eid="none"), se.parse_emitter({}))
    _run(window, 0.5)
    assert backend.players == []


def test_the_editor_hears_nothing(backend: Backend) -> None:
    window = _window(_sprite(0, 0), {"weather_sounds": {"rain": RAIN}}, parse_particles([{"preset": "rain"}]))
    window.audio.scene_music = False  # Mesh Studio's editor
    _emit(window, "stream", 10, 0)
    _run(window, 0.5)
    assert backend.players == []


# ---------------------------------------------------------------- weather
def test_rain_is_heard_as_hard_as_it_falls_and_fades_when_it_stops(backend: Backend) -> None:
    effects = parse_particles([{"preset": "rain", "count": 3000}])
    window = _window(_sprite(0, 0), {"weather_sounds": {"rain": RAIN, "rain_volume": 0.6}}, effects)
    _run(window, 6.0)
    rain = window.audio._loops["weather:rain"]
    assert rain.volume == pytest.approx(0.6, abs=0.01)
    window.scene_particles.enabled[0] = False  # the rain stops (the particle layer's own switch)
    levels = []
    for _ in range(16):
        _run(window, 0.5)
        levels.append(rain.volume if "weather:rain" in window.audio.loops() else 0.0)
    assert levels[0] > 0.3 and levels[5] < 0.1 and levels[-1] == 0.0  # most of it gone in 3 s, silent by 8
    assert all(a >= b for a, b in zip(levels, levels[1:]))  # eased out, never back up
    window.scene_particles.enabled[0] = True
    _run(window, 6.0)
    assert len([p for p in backend.players if p.path == RAIN]) == 2  # once more after it had stopped: never per frame


def test_light_rain_is_quieter_than_steady(backend: Backend) -> None:
    def heard(count: int) -> float:
        window = _window(_sprite(0, 0), {"weather_sounds": {"rain": RAIN}}, parse_particles([{"preset": "rain", "count": count}]))
        _run(window, 8.0)
        return float(window.audio._loops["weather:rain"].volume)

    assert heard(1200) < heard(3000) * 0.5


def test_the_wind_follows_its_gusts_without_restarting(backend: Backend) -> None:
    window = _window(_sprite(0, 0), {"weather_sounds": {"wind": WIND}, "wind": {"speed": 9.0, "gust": 0.9}})
    levels = []
    for _ in range(40):
        _run(window, 0.5)
        levels.append(window.audio._loops["weather:wind"].volume)
    assert max(levels) - min(levels) > 0.05  # gusts swell and drop
    assert len(backend.players) == 1
    calm = _window(_sprite(0, 0), {"weather_sounds": {"wind": WIND}})
    _run(calm, 2.0)
    assert "weather:wind" not in calm.audio.loops()


def test_a_room_with_the_same_rain_keeps_the_same_loop(backend: Backend) -> None:
    settings = {"weather_sounds": {"rain": RAIN}}
    effects = parse_particles([{"preset": "rain"}])
    window = _window(_sprite(0, 0), settings, effects)
    _run(window, 3.0)
    se.reset(window, "next_room", settings)
    _run(window, 3.0)
    assert len(backend.players) == 1


def test_many_sounds_together_are_scaled_down_not_piled_up(backend: Backend) -> None:
    effects = parse_particles([{"preset": "rain", "count": 6000}])
    window = _window(_sprite(0, 0), {"weather_sounds": {"rain": RAIN, "wind": WIND, "rain_volume": 1.0, "wind_volume": 1.0},
                                     "wind": {"speed": 20.0}}, effects)
    for i, sound in enumerate((WATER, BIRDS, "assets/ambience/x.wav")):
        se.soundscape_of(window).register(_sprite(5, 5, eid=f"e{i}"), se.parse_emitter({"sound": sound, "volume": 1.0}))
    _run(window, 8.0)
    total = sum(t.volume * t.scale for t in window.audio._loops.values())
    assert total == pytest.approx(se.HEADROOM, abs=0.1)


# ---------------------------------------------------------------- the audio manager's loops (narrow M21B extension)
def test_a_loop_asked_for_every_frame_keeps_its_fade_and_takes_pan(backend: Backend) -> None:
    audio = AudioManager()
    audio.play_loop("k", WATER, volume=0.5, fade_in_s=1.0, pan=-0.5)
    for _ in range(30):  # half a second of frames, each asking again
        audio.play_loop("k", WATER, volume=0.5, fade_in_s=1.0, pan=-0.5)
        audio.update(1 / 60)
    track = audio._loops["k"]
    assert track.scale == pytest.approx(0.5, abs=0.02)  # half-way through its 1 s fade: not restarted each frame
    assert backend.players[0].position[0] == pytest.approx(-0.5)
    audio.play_loop("k", WATER, volume=0.5, pan=0.3)
    assert backend.players[0].position[0] == pytest.approx(0.3) and len(backend.players) == 1


def test_a_loop_stopped_and_asked_for_again_before_it_faded_is_revived(backend: Backend) -> None:
    audio = AudioManager()
    audio.play_loop("k", WATER)
    audio.stop_loop("k", fade_out_s=1.0)
    audio.update(0.3)
    audio.play_loop("k", WATER, fade_in_s=0.5)
    audio.update(0.6)
    assert len(backend.players) == 1 and audio._loops["k"].scale == pytest.approx(1.0)


def test_a_one_shot_emitter_plays_once_each_time_the_player_comes_near(backend: Backend) -> None:
    player = _sprite(0, 0)
    window = _window(player)
    _emit(window, "bell", 0, 0, loop=False, distance=200, radius=32, fade_in=0.0, fade_out=0.0)
    _run(window, 1.0)
    assert len(backend.players) == 1 and backend.players[0].loop is False
    player.center_x = 1000  # away (out of reach): stopped
    _run(window, 0.5)
    player.center_x = 0  # back: once more
    _run(window, 0.5)
    assert len(backend.players) == 2
