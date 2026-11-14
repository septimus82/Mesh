"""A room's environmental sound (Milestone 21B): sound emitters placed in it, and its weather heard.

**A sound emitter** is an object with the ``SoundEmitter`` behaviour (Mesh Studio: Objects > Sound), so it is
placed, moved, copied, deleted, undone and saved like any object, in 2D and HD-2D rooms alike::

    {"id": "pond_water", "x": 1408, "y": 992, "elevation": -14, "behaviours": ["SoundEmitter"],
     "behaviour_config": {"SoundEmitter": {"sound": "assets/ambience/stream_loop.wav", "volume": 0.8,
                                           "radius": 96, "distance": 480}}}

- ``sound``: the file (WAV plays everywhere; OGG and MP3 need the system's decoders: ``docs/audio.md``);
- ``volume`` (0-1): at full strength; ``radius`` (px): full strength within it; ``distance`` (px): heard up to it.
  Between them it fades smoothly (a smoothstep: no sudden change at either edge). An HD-2D room's heights count:
  an emitter 3 m up a hill is 3 m further from someone at its foot;
- ``stereo``: heard from its side (panned by where it is from the listener; less so close by); ``loop``: plays
  round (off: once each time the listener comes within reach); ``enabled``; ``fade_in`` / ``fade_out`` (s): when it
  starts and stops.

The listener is the player (else the camera's centre). Only emitters within reach play: one out of reach has no
player at all (nothing decoded), and the loudest ``MAX_ACTIVE`` play at once, at most ``MAX_SAME_SOUND`` of one
file (more copies of one sound add little but loudness). Their players are the ambience bus's keyed loops
(``AudioManager.play_loop``): an emitter in reach every frame only has its volume and pan set.

**Weather heard:** a room's ``settings.weather_sounds`` names its rain and wind sounds::

    "weather_sounds": {"rain": "assets/ambience/rain_loop.wav", "wind": "assets/ambience/wind_loop.wav",
                       "rain_volume": 0.6, "wind_volume": 0.5}

The rain's loudness follows the rain actually falling (``engine.water.rain_rate`` over the room's particle effects
and which are on: what makes the ripples), the wind's follows the wind where the listener is (the room's
``settings.wind`` with its gusts: ``engine.wind.speed_at``). Both ease (about a second), so rain that stops fades
out, and a room entered with the same rain keeps the same loop playing (keys ``weather:rain``, ``weather:wind``).
An indoor room has no rain (``weather_exposure``), so none is heard; muffled weather indoors is Milestone 21C.

**Loudness together:** when the ambience playing would add up past ``HEADROOM`` (about two full-strength
sounds), every ambience level is scaled down together, smoothly, so a stream beside rain beside wind never piles up.

**Lifecycle:** a room's emitters register as its objects are made (``reset`` empties the list when a room starts
loading); the first update after that stops the loops of emitters no longer there. Mesh Studio's editor turns room
sound off with the music (``AudioManager.scene_music``): emitters play in play-tests only."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from engine.logging_tools import get_logger

logger = get_logger(__name__)

PX_PER_M = 32.0
MAX_ACTIVE = 12  # emitters playing at once (the loudest)
MAX_SAME_SOUND = 3  # of them, at most this many of one file
STARTS_PER_FRAME = 2  # emitters starting in one frame (opening a stream costs ~3 ms): the rest start next frame
HEADROOM = 1.6  # the ambience levels' sum above which all are scaled down together
EASE_S = 0.12  # s: an emitter's level follows the listener this quickly (no zipper noise on a jump)
WEATHER_EASE_S = 1.2  # s: rain and wind loudness follow the weather this gently
SILENT = 0.003  # a level below this is silence: its loop stops
RESEND = 0.002  # a loop's volume is set again once what it should play differs from what it was given by this
STOP_BEYOND = 1.1  # an emitter stops once the listener is this many times its distance away (+ 16 px)
STEREO_WIDTH = 0.75  # the most an emitter is panned (never hard into one ear)
WIND_LOUD_AT = 14.0  # m/s: the wind's sound is at full strength from this speed
SOUND_FILES = (".wav", ".ogg", ".mp3")

_FIELDS = ("sound", "volume", "radius", "distance", "stereo", "loop", "enabled", "fade_in", "fade_out")


class EmitterError(ValueError):
    """A sound emitter's settings can't be used."""


@dataclass(frozen=True)
class Emitter:
    sound: str = ""
    volume: float = 0.8
    radius: float = 64.0  # px: full strength within it
    distance: float = 320.0  # px: heard up to it
    stereo: bool = True
    loop: bool = True
    enabled: bool = True
    fade_in: float = 1.0  # s
    fade_out: float = 1.0  # s


DEFAULT = Emitter()


def parse_emitter(raw: Any, where: str = "SoundEmitter") -> Emitter:
    """A ``SoundEmitter`` config checked, completed from the defaults. The sound may be "" (none chosen yet)."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise EmitterError(f"{where} must be an object like {{\"sound\": \"assets/ambience/stream_loop.wav\"}}")
    unknown = set(raw) - set(_FIELDS)
    if unknown:
        raise EmitterError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
    sound = raw.get("sound", "")
    if not isinstance(sound, str):
        raise EmitterError(f"{where}.sound must be a file path (got {sound!r})")
    if sound and not sound.lower().endswith(SOUND_FILES):
        raise EmitterError(f"{where}.sound must be a .wav, .ogg or .mp3 file (got {sound!r})")

    def number(key: str, lo: float, hi: float) -> float:
        value = raw.get(key, getattr(DEFAULT, key))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or not lo <= value <= hi:
            raise EmitterError(f"{where}.{key} must be a number from {lo:g} to {hi:g} (got {value!r})")
        return float(value)

    def flag(key: str) -> bool:
        value = raw.get(key, getattr(DEFAULT, key))
        if not isinstance(value, bool):
            raise EmitterError(f"{where}.{key} must be true or false (got {value!r})")
        return value

    radius, distance = number("radius", 0.0, 8192.0), number("distance", 8.0, 16384.0)
    if radius >= distance:
        raise EmitterError(f"{where}: its full-strength radius ({radius:g} px) must be less than how far it is heard "
                           f"({distance:g} px)")
    return Emitter(sound=sound.strip(), volume=number("volume", 0.0, 1.0), radius=radius, distance=distance,
                   stereo=flag("stereo"), loop=flag("loop"), enabled=flag("enabled"),
                   fade_in=number("fade_in", 0.0, 30.0), fade_out=number("fade_out", 0.0, 30.0))


def gain(distance: float, emitter: Emitter) -> float:
    """0..1 at ``distance`` px: 1 within its radius, 0 from its distance on, a smoothstep between."""
    if distance <= emitter.radius:
        return 1.0
    if distance >= emitter.distance:
        return 0.0
    t = (distance - emitter.radius) / (emitter.distance - emitter.radius)
    return 1.0 - t * t * (3.0 - 2.0 * t)


def pan(dx: float, distance: float, emitter: Emitter) -> float:
    """-1..1: how far to the listener's left or right it sounds (its direction's sideways part, at most
    ``STEREO_WIDTH``); within its radius less so, centred where it is (you're inside the sound)."""
    if not emitter.stereo or distance <= 1e-6:
        return 0.0
    side = dx / max(distance, emitter.radius, 1.0)
    return max(-1.0, min(1.0, side)) * STEREO_WIDTH


@dataclass(frozen=True)
class WeatherSounds:
    rain: str = ""
    wind: str = ""
    rain_volume: float = 0.6
    wind_volume: float = 0.5


def parse_weather_sounds(raw: Any, where: str = "settings.weather_sounds") -> WeatherSounds:
    """A room's ``settings.weather_sounds`` checked (None: no weather heard)."""
    if raw is None:
        return WeatherSounds()
    if not isinstance(raw, dict):
        raise EmitterError(f"{where} must be an object like {{\"rain\": \"assets/ambience/rain_loop.wav\"}}")
    unknown = set(raw) - {"rain", "wind", "rain_volume", "wind_volume"}
    if unknown:
        raise EmitterError(f"{where}: unknown setting(s) {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    for key in ("rain", "wind"):
        value = raw.get(key, "")
        if not isinstance(value, str) or (value and not value.lower().endswith(SOUND_FILES)):
            raise EmitterError(f"{where}.{key} must be a .wav, .ogg or .mp3 file (got {value!r})")
        out[key] = value.strip()
    for key in ("rain_volume", "wind_volume"):
        value = raw.get(key, getattr(WeatherSounds(), key))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise EmitterError(f"{where}.{key} must be a number from 0 to 1 (got {value!r})")
        out[key] = float(value)
    return WeatherSounds(**out)


LIBRARY = "assets/ambience"  # Mesh's own loops (CC0; tooling/make_ambience_library.py): Studio copies a chosen one in


def library() -> list[Any]:
    """Mesh's ambience library: the engine's ``assets/ambience/*.wav`` (a checkout's, or a pip install's)."""
    from engine.repo_root import bundled_dir  # noqa: PLC0415

    folder = bundled_dir(LIBRARY)
    return sorted(folder.glob("*.wav")) if folder.is_dir() else []


def sound_problem(path: Any) -> str | None:
    """Why the sound file at ``path`` (a Path) can't be used here, or None: missing, not a sound file, or one this
    computer has no decoder for (an OGG or MP3 without the system's decoders)."""
    from pathlib import Path  # noqa: PLC0415

    path = Path(path)
    if not path.is_file():
        return f"There's no sound file at {path}."
    if path.suffix.lower() not in SOUND_FILES:
        return f"{path.name} isn't a sound file Mesh plays (.wav, .ogg or .mp3)."
    try:
        import pyglet  # noqa: PLC0415

        source = pyglet.media.load(str(path), streaming=True)
        if not source.duration or source.audio_format is None:
            return f"{path.name} holds no sound."
    except Exception as exc:  # noqa: BLE001  # REASON: any decoder failure is the creator's answer, said in words
        from engine.swallowed_exceptions import _log_swallow  # noqa: PLC0415

        _log_swallow("SNDE-001", f"engine.sound_emitters: {path.name} can't be decoded here")
        return (f"Mesh can't play {path.name} on this computer ({type(exc).__name__}). WAV plays everywhere; "
                f"OGG and MP3 need the system's decoders.")
    return None


# ---------------------------------------------------------------------------------------------------- runtime
@dataclass
class _Live:
    """An emitter in the room: where it is (px; z: its elevation) and how loud it is now."""

    key: str
    entity: Any
    emitter: Emitter
    level: float = 0.0  # what it plays at now (eased toward its target)
    playing: bool = False
    pan: float = 0.0
    sent: tuple[float, float] = (-1.0, 0.0)  # the volume and pan its loop was last given


@dataclass
class Soundscape:
    """The room's emitters and weather, heard from the listener; one per game window (``window.soundscape``)."""

    emitters: list[_Live] = field(default_factory=list)
    stale: set[str] = field(default_factory=set)  # loops of the last room's emitters, to stop unless still here
    weather: WeatherSounds = field(default_factory=WeatherSounds)
    wind: Any = None  # engine.wind.Wind (None: calm)
    levels: dict[str, float] = field(default_factory=dict)  # "rain"/"wind": what they play at now
    sent: dict[str, tuple[float, str]] = field(default_factory=dict)  # "rain"/"wind": the volume and file last given
    headroom: float = 1.0  # the common scale (1: nothing scaled down)
    time: float = 0.0
    room: str = ""
    player: Any = None  # the listener, found once per room
    updates: int = 0
    loop_calls: int = 0  # play_loop / stop_loop calls made (diagnostics: the per-frame cost)

    def register(self, entity: Any, emitter: Emitter) -> None:
        data = getattr(entity, "mesh_entity_data", None) or {}
        key = f"emitter:{self.room}:{data.get('id') or id(entity)}"
        self.emitters.append(_Live(key, entity, emitter))
        self.stale.discard(key)

    def diagnostics(self) -> dict[str, Any]:
        return {"emitters": len(self.emitters), "playing": sorted(e.key for e in self.emitters if e.playing),
                "levels": {e.key: round(e.level, 3) for e in self.emitters if e.playing},
                "weather": {k: round(v, 3) for k, v in self.levels.items()}, "headroom": round(self.headroom, 3),
                "updates": self.updates, "loop_calls": self.loop_calls}


def soundscape_of(window: Any) -> Soundscape:
    scape = getattr(window, "soundscape", None)
    if not isinstance(scape, Soundscape):
        scape = Soundscape()
        window.soundscape = scape
    return scape


def reset(window: Any, room: str = "", settings: Any = None) -> None:
    """A room starts loading: its emitters register as its objects are made; the last room's loops stop at the next
    update unless the same emitters are back. Its weather sounds and wind are read from its settings."""
    scape = soundscape_of(window)
    scape.stale |= {e.key for e in scape.emitters if e.playing}
    scape.emitters, scape.room, scape.player = [], room, None
    settings = settings if isinstance(settings, dict) else {}
    try:
        scape.weather = parse_weather_sounds(settings.get("weather_sounds"))
    except EmitterError as exc:
        scape.weather = WeatherSounds()
        logger.warning("[Mesh][Audio] this room's weather sounds are off: %s", exc)
    from engine.wind import WindError, parse_wind  # noqa: PLC0415

    try:
        scape.wind = parse_wind(settings.get("wind"))
    except WindError:
        scape.wind = None  # (its particles say so already)


def _listener(window: Any, scape: Soundscape) -> tuple[float, float, float] | None:
    """The player's place (px; z: its elevation px), else the camera's centre."""
    controller = getattr(window, "scene_controller", None)
    player = scape.player
    if player is None or getattr(player, "sprite_lists", True) == []:  # (removed from the room)
        find = getattr(controller, "_find_player_sprite", None)
        player = find() if callable(find) else None
        scape.player = player
    if player is not None:
        data = getattr(player, "mesh_entity_data", None) or {}
        z = data.get("elevation", 0.0)
        return (float(player.center_x), float(player.center_y),
                float(z) if isinstance(z, (int, float)) and not isinstance(z, bool) else 0.0)
    from engine.audio import _resolve_listener_pos  # noqa: PLC0415

    at = _resolve_listener_pos(window)
    return (at[0], at[1], 0.0) if at is not None else None


def _rain_rate(window: Any) -> float:
    from engine.water import rain_rate  # noqa: PLC0415

    renderer = getattr(window, "hd2d_renderer", None)
    layer = getattr(renderer, "particles", None) if renderer is not None else getattr(window, "scene_particles", None)
    return rain_rate(layer.effects, layer.enabled) if layer is not None else 0.0


def _ease(now: float, target: float, dt: float, seconds: float) -> float:
    return target if seconds <= 0 else now + (target - now) * min(1.0, dt / seconds)


def update(window: Any, dt: float) -> None:
    """Every frame: each emitter's loudness and pan from where the listener is, the weather's from the weather."""
    audio = getattr(window, "audio", None)
    scape = getattr(window, "soundscape", None)
    if audio is None or not isinstance(scape, Soundscape) or not getattr(audio, "scene_music", True):
        return
    dt = max(0.0, float(dt))
    scape.time += dt
    scape.updates += 1
    for key in scape.stale:  # the last room's emitters that aren't here
        audio.stop_loop(key, fade_out_s=1.0)
        scape.loop_calls += 1
    scape.stale.clear()
    listener = _listener(window, scape)
    if listener is None:
        return
    lx, ly, lz = listener

    targets: dict[str, tuple[float, float, float]] = {}  # key -> (target level, pan, distance)
    for live in scape.emitters:
        e = live.emitter
        if not e.enabled or not e.sound:
            continue
        data = getattr(live.entity, "mesh_entity_data", None) or {}
        z = data.get("elevation", 0.0)
        z = float(z) if isinstance(z, (int, float)) and not isinstance(z, bool) else 0.0
        dx, dy = float(live.entity.center_x) - lx, float(live.entity.center_y) - ly
        d = math.sqrt(dx * dx + dy * dy + (z - lz) ** 2)
        if d < e.distance * STOP_BEYOND + 16.0:
            targets[live.key] = (e.volume * gain(d, e), pan(dx, d, e), d)
    chosen: set[str] = set()
    per_sound: dict[str, int] = {}
    by_key = {live.key: live for live in scape.emitters}
    for key in sorted(targets, key=lambda k: -targets[k][0]):  # the loudest first
        sound = by_key[key].emitter.sound
        if len(chosen) < MAX_ACTIVE and per_sound.get(sound, 0) < MAX_SAME_SOUND and (
                targets[key][0] > SILENT or by_key[key].playing):
            chosen.add(key)
            per_sound[sound] = per_sound.get(sound, 0) + 1

    weather = scape.weather
    rain_target = min(1.0, _rain_rate(window)) * weather.rain_volume if weather.rain else 0.0
    wind_target = 0.0
    if weather.wind and scape.wind is not None and not scape.wind.calm:
        from engine.wind import speed_at  # noqa: PLC0415

        speed = speed_at(lx / PX_PER_M, ly / PX_PER_M, scape.time, scape.wind)
        wind_target = min(1.0, speed / WIND_LOUD_AT) ** 0.7 * weather.wind_volume
    total = sum(targets[k][0] for k in chosen) + rain_target + wind_target
    scape.headroom = _ease(scape.headroom, min(1.0, HEADROOM / total) if total > 0 else 1.0, dt, 0.5)

    starts = 0
    for live in scape.emitters:
        e = live.emitter
        if live.key in chosen and not live.playing:
            if starts >= STARTS_PER_FRAME:
                continue  # (a crowded room entered: they start over the next frames, each fading in)
            starts += 1
        if live.key in chosen:
            target, side, _d = targets[live.key]
            level = _ease(live.level, target, dt, EASE_S) if live.playing else target
            volume = level * scape.headroom
            if not live.playing or abs(volume - live.sent[0]) > RESEND or abs(side - live.sent[1]) > 0.01:
                ok = audio.play_loop(live.key, e.sound, volume=volume,
                                     fade_in_s=0.0 if live.playing else e.fade_in, pan=side, loop=e.loop)
                scape.loop_calls += 1
                live.playing, live.sent = ok, (volume, side)
            live.level, live.pan = level, side
        elif live.playing:
            audio.stop_loop(live.key, fade_out_s=e.fade_out)
            scape.loop_calls += 1
            live.playing, live.level, live.sent = False, 0.0, (-1.0, 0.0)

    for name, path, target in (("rain", weather.rain, rain_target), ("wind", weather.wind, wind_target)):
        key = f"weather:{name}"
        level = _ease(scape.levels.get(name, 0.0), target, dt, WEATHER_EASE_S)
        playing = key in audio.loops()
        volume = level * scape.headroom
        if path and level > SILENT:
            sent_volume, sent_path = scape.sent.get(name, (-1.0, ""))
            if not playing or sent_path != path or abs(volume - sent_volume) > RESEND:  # (a room's own file too)
                audio.play_loop(key, path, volume=volume)
                scape.loop_calls += 1
                scape.sent[name] = (volume, path)
        elif playing:
            audio.stop_loop(key, fade_out_s=0.5)
            scape.loop_calls += 1
            level = 0.0
            scape.sent.pop(name, None)
        scape.levels[name] = level
