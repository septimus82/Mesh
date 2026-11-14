"""M21A: scene music semantics, real crossfades, the music / ambience / sfx buses, and player cleanup.

A stand-in backend records every player made and released, so overlap, reuse and leaks are counted exactly.
Headless; nothing is played aloud (the real-backend check is ``tooling/audio_smoke.py``)."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

import engine.audio as audio_mod
from engine.audio import MAX_FADING_TRACKS, AudioManager
from engine.scene_lifecycle_controller import apply_scene_music
from engine.scene_loader import DEFAULT_SETTINGS, SceneLoader
from engine.scene_runtime import saved_world
from engine.scene_serializer import compact_scene_payload

pytestmark = pytest.mark.fast

A, B, C, D = (f"assets/music/{n}.wav" for n in ("a", "b", "c", "d"))


class FakePlayer:
    def __init__(self, path: str, loop: bool) -> None:
        self.path, self.loop, self.volume, self.released = path, loop, 0.0, False

    def pause(self) -> None:
        self.released = True


class Backend:
    """``arcade.Sound`` and ``arcade.stop_sound`` stand-ins: every player made, and which were released."""

    def __init__(self, missing: tuple[str, ...] = ()) -> None:
        self.players: list[FakePlayer] = []
        self.loads: list[str] = []
        self.missing = missing

    def sound(self, path: Any, streaming: bool = False) -> Any:
        name = str(path).replace("\\", "/")
        self.loads.append(name)
        if any(name.endswith(m) for m in self.missing):
            raise FileNotFoundError(name)
        assert streaming, "music and ambience stream"

        def play(volume: float = 1.0, loop: bool = False) -> FakePlayer:
            player = FakePlayer(name, loop)
            player.volume = volume
            self.players.append(player)
            return player

        return SimpleNamespace(play=play)

    def stop(self, player: FakePlayer) -> None:
        assert not player.released, "released twice"
        player.released = True

    def live(self) -> list[FakePlayer]:
        return [p for p in self.players if not p.released]

    def playing(self, path: str) -> list[FakePlayer]:
        return [p for p in self.live() if p.path.endswith(path)]


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Backend:
    fake = Backend()
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "stop_sound", fake.stop)
    monkeypatch.setattr(audio_mod, "resolve_path", lambda p: p)
    return fake


def _window(audio: AudioManager, **cfg: Any) -> SimpleNamespace:
    return SimpleNamespace(audio=audio, engine_config=SimpleNamespace(**cfg))


def _enter(window: SimpleNamespace, settings: dict[str, Any]) -> None:
    """A room entered: its settings as the loader gives them (defaults applied)."""
    apply_scene_music(window, SceneLoader()._apply_scene_defaults({"settings": settings}, migrated=True)["settings"])


# ---------------------------------------------------------------- scene music semantics
def test_the_loader_no_longer_turns_a_missing_music_setting_into_silence() -> None:
    """The defect (reproduced first): DEFAULT_SETTINGS held "music": None, so every room without music stopped it."""
    assert "music" not in DEFAULT_SETTINGS
    loaded = SceneLoader()._apply_scene_defaults({"settings": {}}, migrated=True)
    assert "music" not in loaded["settings"]
    explicit = SceneLoader()._apply_scene_defaults({"settings": {"music": None}}, migrated=True)
    assert "music" in explicit["settings"] and explicit["settings"]["music"] is None


def test_an_explicit_silence_survives_compact_saving() -> None:
    """The compact serializer drops settings equal to their defaults: it used to drop an authored "music": null."""
    assert compact_scene_payload({"settings": {"music": None, "background_color": "black"}})["settings"] == {
        "music": None}


def test_a_room_without_music_keeps_the_music_playing(backend: Backend) -> None:
    window = _window(AudioManager())
    _enter(window, {"music": A})
    player = backend.playing(A)[0]
    _enter(window, {})
    assert window.audio.music_path == A and backend.live() == [player]


def test_explicit_silence_stops_the_music(backend: Backend) -> None:
    window = _window(AudioManager())
    for silence in (None, "", "   "):
        _enter(window, {"music": A})
        _enter(window, {"music": silence})
        assert window.audio.music_path is None and backend.live() == []


def test_the_track_already_playing_carries_on_uninterrupted(backend: Backend) -> None:
    """Same track in the next room (or the same room again): no restart, no second player; its volume eased."""
    window = _window(AudioManager())
    _enter(window, {"music": A, "music_volume": 1.0})
    player = backend.playing(A)[0]
    _enter(window, {"music": A, "music_volume": 0.5})
    _enter(window, {"music": A, "music_volume": 0.5})
    assert backend.loads.count(A) == 1 and backend.live() == [player]
    assert player.volume == pytest.approx(0.5)


def test_a_new_track_crossfades_both_playing_during_the_overlap(backend: Backend) -> None:
    window = _window(AudioManager(), music_crossfade_enabled=True, music_crossfade_out_s=1.0, music_crossfade_in_s=1.0)
    _enter(window, {"music": A})
    window.audio.update(1.0)
    a = backend.playing(A)[0]
    _enter(window, {"music": B})
    b = backend.playing(B)[0]
    assert window.audio.music_path == B
    levels = []
    for _ in range(4):
        window.audio.update(0.2)
        levels.append((a.volume, b.volume))
        assert not a.released and not b.released  # both play during the overlap
    assert [x for x, _ in levels] == sorted([x for x, _ in levels], reverse=True)  # A falls
    assert [y for _, y in levels] == sorted(y for _, y in levels)  # B rises
    assert levels[1][0] == pytest.approx(0.6) and levels[1][1] == pytest.approx(0.4)
    window.audio.update(0.3)
    assert a.released and b.volume == pytest.approx(1.0) and backend.live() == [b]


def test_going_straight_back_fades_the_old_track_back_in_not_restarted(backend: Backend) -> None:
    window = _window(AudioManager(), music_crossfade_enabled=True, music_crossfade_out_s=1.0, music_crossfade_in_s=1.0)
    _enter(window, {"music": A})
    window.audio.update(1.0)
    a = backend.playing(A)[0]
    _enter(window, {"music": B})
    window.audio.update(0.5)
    _enter(window, {"music": A})  # back through the door, mid-fade
    window.audio.update(1.0)
    assert backend.loads.count(A) == 1 and backend.live() == [a] and a.volume == pytest.approx(1.0)


def test_rapid_room_changes_cap_the_tracks_fading_and_leave_no_players(backend: Backend) -> None:
    window = _window(AudioManager(), music_crossfade_enabled=True, music_crossfade_out_s=2.0, music_crossfade_in_s=2.0)
    for path in (A, B, C, D, A, B, C, D):
        _enter(window, {"music": path})
        window.audio.update(0.05)
        assert len(backend.live()) <= MAX_FADING_TRACKS + 1
    window.audio.update(3.0)
    assert [p.path for p in backend.live()] == [D]
    window.audio.shutdown()
    assert backend.live() == [] and window.audio.released_players == len(backend.players)


def test_without_crossfade_changes_are_immediate(backend: Backend) -> None:
    window = _window(AudioManager())
    _enter(window, {"music": A})
    _enter(window, {"music": B})
    assert [p.path for p in backend.live()] == [B] and backend.live()[0].volume == pytest.approx(1.0)


def test_a_track_that_cant_be_played_leaves_the_music_as_it_was_and_is_tried_once(
        monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Backend(missing=("gone.wav",))
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "stop_sound", fake.stop)
    monkeypatch.setattr(audio_mod, "resolve_path", lambda p: p)
    errors: list[str] = []
    monkeypatch.setattr(audio_mod.logger, "error", lambda msg, *a: errors.append(msg % a))  # (Mesh loggers don't propagate)
    window = _window(AudioManager())
    _enter(window, {"music": A})
    for _ in range(5):  # rapid room changes into the room whose track is missing
        _enter(window, {"music": "assets/music/gone.wav"})
    assert window.audio.music_path == A and len(fake.live()) == 1
    assert fake.loads.count("assets/music/gone.wav") == 1
    assert sum("gone.wav" in e for e in errors) == 1
    window.audio.reload_cached_sounds(("assets/music/gone.wav",))  # the file changed: tried again
    _enter(window, {"music": "assets/music/gone.wav"})
    assert fake.loads.count("assets/music/gone.wav") == 2


def test_malformed_music_settings_dont_break_the_room(backend: Backend, monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.scene_lifecycle_controller as lifecycle

    warnings: list[str] = []
    monkeypatch.setattr(lifecycle.logger, "warning", lambda msg, *a: warnings.append(msg % a))
    monkeypatch.setattr(lifecycle, "_MUSIC_WARNED", set())
    window = _window(AudioManager(), music_crossfade_enabled="yes")
    _enter(window, {"music": A})
    _enter(window, {"music": 5})  # not a path: as if unset
    _enter(window, {"music": {"track": B}})
    assert window.audio.music_path == A
    _enter(window, {"music": B, "music_volume": "loud", "music_crossfade_out_s": "slow", "music_crossfade_in_s": None})
    assert window.audio.music_path == B
    assert any("settings.music must be a path" in w for w in warnings)
    assert any("music_volume is not a number" in w for w in warnings)


def test_studio_editing_leaves_room_music_alone(backend: Backend) -> None:
    window = _window(AudioManager())
    window.audio.scene_music = False
    _enter(window, {"music": A})
    assert backend.players == []


# ---------------------------------------------------------------- saved games
def _save(meta_music: Any = None, room_ids: tuple[str, ...] = ()) -> dict[str, Any]:
    meta: dict[str, Any] = {saved_world.ROOM_IDS: list(room_ids)}
    if meta_music is not None:
        meta[saved_world.MUSIC] = meta_music
    return {"entities": [], "settings": {}, "meta": meta}


def test_a_loaded_save_plays_the_music_that_was_playing_in_a_room_without_its_own() -> None:
    room = {"settings": {}, "entities": []}
    loaded = saved_world.compose(_save({"path": B, "volume": 0.6}), copy.deepcopy(room), "r.json")
    assert loaded["settings"]["music"] == B and loaded["settings"]["music_volume"] == pytest.approx(0.6)
    silent = saved_world.compose(_save({"path": None}), copy.deepcopy(room), "r.json")
    assert "music" in silent["settings"] and silent["settings"]["music"] is None


def test_a_room_with_its_own_music_wins_and_older_saves_keep_whatever_plays() -> None:
    own = saved_world.compose(_save({"path": B, "volume": 0.6}), {"settings": {"music": A}, "entities": []}, "r.json")
    assert own["settings"]["music"] == A
    older = saved_world.compose(_save(), {"settings": {}, "entities": []}, "r.json")  # saved before M21A
    assert "music" not in older["settings"]


# ---------------------------------------------------------------- buses
def test_each_bus_is_its_volume_times_master_applied_to_what_is_playing(backend: Backend) -> None:
    audio = AudioManager()
    audio.play_music(A, volume=0.8)
    audio.play_loop("pond", "assets/ambience/water.wav", volume=0.5)
    music, loop = backend.playing(A)[0], backend.playing("water.wav")[0]
    audio.set_master_volume(0.5)
    audio.set_music_volume(0.5)
    audio.set_ambience_volume(0.4)
    assert music.volume == pytest.approx(0.8 * 0.5 * 0.5) and loop.volume == pytest.approx(0.5 * 0.4 * 0.5)
    audio.set_ambience_volume(1.0)  # one bus: the other untouched
    assert music.volume == pytest.approx(0.2) and loop.volume == pytest.approx(0.25)
    assert audio.bus_gain("sfx") == pytest.approx(0.5)
    assert len(backend.players) == 2  # nothing restarted


def test_volume_changes_during_a_crossfade_apply_to_both_tracks(backend: Backend) -> None:
    audio = AudioManager()
    audio.play_music(A)
    audio.transition_music(B, fade_out_s=1.0, fade_in_s=1.0)
    audio.update(0.5)
    audio.set_music_volume(0.5)
    a, b = backend.playing(A)[0], backend.playing(B)[0]
    assert a.volume == pytest.approx(0.25) and b.volume == pytest.approx(0.25)


def test_muting_is_predictable_and_unmuting_restores(backend: Backend, monkeypatch: pytest.MonkeyPatch) -> None:
    audio = AudioManager()
    audio.set_music_volume(0.6)
    audio.play_music(A)
    audio.play_loop("wind", "assets/ambience/wind.wav")
    music, loop = backend.playing(A)[0], backend.playing("wind.wav")[0]
    sfx: list[float] = []
    monkeypatch.setattr(audio, "get_sound", lambda _p: object())
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "play_sound", lambda _s, volume=1.0, **_k: sfx.append(volume))
    audio.set_muted(True)
    audio.play_sound("assets/sounds/hit.wav")
    assert (music.volume, loop.volume, sfx) == (0.0, 0.0, [])
    audio.set_muted(True, "music")
    audio.set_muted(False)  # master back; music still muted on its own
    assert music.volume == 0.0 and loop.volume == pytest.approx(1.0)
    audio.set_muted(False, "music")
    assert music.volume == pytest.approx(0.6) and audio.music_volume == pytest.approx(0.6)
    audio.play_sound("assets/sounds/hit.wav")
    assert sfx == [pytest.approx(1.0)]
    with pytest.raises(ValueError):
        audio.set_muted(True, "voice")


def test_a_sound_effect_never_touches_the_music(backend: Backend, monkeypatch: pytest.MonkeyPatch) -> None:
    audio = AudioManager()
    audio.play_music(A)
    music = backend.playing(A)[0]
    monkeypatch.setattr(audio, "get_sound", lambda _p: object())
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "play_sound", lambda *_a, **_k: None)
    audio.play_sound("assets/sounds/hit.wav")
    audio.play_sound_at("assets/sounds/hit.wav", (10.0, 0.0), listener_pos=(0.0, 0.0))
    assert backend.live() == [music] and music.volume == pytest.approx(1.0)


# ---------------------------------------------------------------- ambience loops (the M21B seam)
def test_an_ambience_loop_asked_for_again_is_not_duplicated(backend: Backend) -> None:
    audio = AudioManager()
    for volume in (1.0, 0.5, 0.5):  # the room loaded three times
        assert audio.play_loop("pond", "assets/ambience/water.wav", volume=volume)
    assert len(backend.players) == 1 and backend.players[0].loop is True
    assert backend.players[0].volume == pytest.approx(0.5)
    audio.play_loop("pond", "assets/ambience/rain.wav", fade_in_s=1.0)  # another sound: crossfaded
    audio.update(1.0)
    assert [p.path for p in backend.live()] == ["assets/ambience/rain.wav"]
    audio.stop_loop("pond", fade_out_s=0.5)
    audio.update(0.6)
    assert backend.live() == [] and audio.loops() == {}


def test_shutdown_releases_every_player(backend: Backend) -> None:
    audio = AudioManager()
    audio.play_music(A)
    audio.transition_music(B, fade_out_s=5.0, fade_in_s=5.0)
    audio.play_loop("wind", "assets/ambience/wind.wav")
    audio.shutdown()
    assert backend.live() == [] and audio.released_players == 3
    assert audio.diagnostics()["live_players"] == 0


def test_play_music_still_restarts_from_the_top(backend: Backend) -> None:
    """The explicit call (the console's ``music``) keeps its meaning: play from the start, nothing faded."""
    audio = AudioManager()
    audio.play_music(A)
    audio.play_music(A)
    assert backend.loads.count(A) == 2 and len(backend.live()) == 1


def test_a_missing_sound_effect_is_logged_once_not_on_every_play(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing footstep file used to log an error (and look on disk) on every step."""
    fake = Backend(missing=("step.wav",))
    monkeypatch.setattr(audio_mod.optional_arcade.arcade, "Sound", fake.sound)
    monkeypatch.setattr(audio_mod, "resolve_path", lambda p: p)
    errors: list[str] = []
    monkeypatch.setattr(audio_mod.logger, "error", lambda msg, *a: errors.append(msg % a))
    audio = AudioManager()
    for _ in range(10):
        audio.play_sound("assets/sounds/step.wav")
    assert fake.loads.count("assets/sounds/step.wav") == 1 and len(errors) == 1
    audio.reload_cached_sounds(("assets/sounds/step.wav",))  # the file changed: tried again
    audio.play_sound("assets/sounds/step.wav")
    assert fake.loads.count("assets/sounds/step.wav") == 2
