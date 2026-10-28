"""Audio caching and playback helpers for Mesh Engine."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import hypot
from pathlib import Path
from typing import Any, Dict

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from .logging_tools import get_logger
from .paths import resolve_path

logger = get_logger(__name__)

WORLD_SFX_PROFILES: Dict[str, Dict[str, float | bool]] = {
    "melee": {"max_dist": 650.0},
    "projectile": {"max_dist": 900.0},
    "attack": {"max_dist": 700.0},
}
WORLD_SFX_OCCLUDED_VOLUME_MUL: float = 0.35
WORLD_SFX_OCCLUDED_PAN_MUL: float = 0.4
_HOT_RELOAD_AUDIO_EXTENSIONS: tuple[str, ...] = (".wav", ".ogg", ".mp3")
BUSES: tuple[str, ...] = ("music", "ambience", "sfx")  # each scaled by the master volume
MAX_FADING_TRACKS = 3  # tracks still fading out; older ones are cut, so rapid room changes can't pile up players


def _as_xy(pos: Any) -> tuple[float, float] | None:
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        return None
    try:
        return (float(pos[0]), float(pos[1]))
    except Exception:
        _log_swallow("AUDO-001", "engine.audio blanket exception fallback")
        return None


def _attenuate(distance: float, max_dist: float, rolloff: str = "linear") -> float:
    """Return a normalized gain [0..1] for a distance/rolloff pair."""
    dist = max(0.0, float(distance))
    md = max(1e-9, float(max_dist))
    if dist >= md:
        return 0.0
    norm = dist / md
    mode = str(rolloff or "linear").strip().lower()
    if mode in {"inv", "inverse"}:
        return 1.0 / (1.0 + 2.0 * norm)
    if mode in {"square", "quadratic"}:
        return max(0.0, 1.0 - (norm * norm))
    # Default linear rolloff.
    return max(0.0, 1.0 - norm)


def _pan(dx: float, max_pan: float = 1.0) -> float:
    """Return a clamped pan value in [-max_pan, +max_pan]."""
    limit = max(0.0, float(max_pan))
    value = float(dx)
    if value < -limit:
        return -limit
    if value > limit:
        return limit
    return value


def _resolve_listener_pos(window: Any) -> tuple[float, float] | None:
    """Best-effort listener position from lightweight runtime camera state."""
    if window is None:
        return None

    scene_controller = getattr(window, "scene_controller", None)
    scene_camera = getattr(scene_controller, "camera", None) if scene_controller is not None else None
    if scene_camera is not None:
        get_center = getattr(scene_camera, "get_camera_center", None)
        if callable(get_center):
            center = _as_xy(get_center())
            if center is not None:
                return center
        center = _as_xy(getattr(scene_camera, "center", None))
        if center is not None:
            return center
        center = _as_xy(getattr(scene_camera, "position", None))
        if center is not None:
            return center

    camera = getattr(window, "camera", None)
    if camera is not None:
        get_center = getattr(camera, "get_camera_center", None)
        if callable(get_center):
            center = _as_xy(get_center())
            if center is not None:
                return center
        center = _as_xy(getattr(camera, "center", None))
        if center is not None:
            return center
        center = _as_xy(getattr(camera, "position", None))
        if center is not None:
            return center

    get_window_center = getattr(window, "get_camera_center", None)
    if callable(get_window_center):
        center = _as_xy(get_window_center())
        if center is not None:
            return center
    return None


def _is_occluded(
    window: Any,
    listener_pos: tuple[float, float],
    world_pos: tuple[float, float],
) -> bool:
    """Best-effort occlusion query for world SFX.

    This method is intentionally duck-typed and cheap: it performs at most one
    query call (first available callable in preferred order). Missing or
    failing query hooks default to ``False`` (not occluded).
    """
    if window is None:
        return False
    scene_controller = getattr(window, "scene_controller", None)
    lookup_targets = (scene_controller, window)
    query_order: tuple[tuple[str, bool], ...] = (
        ("is_sound_occluded", False),
        ("is_occluded", False),
        ("has_line_of_sight", True),
        ("line_of_sight_clear", True),
    )
    for target in lookup_targets:
        if target is None:
            continue
        for name, invert in query_order:
            query = getattr(target, name, None)
            if not callable(query):
                continue
            try:
                result = query(listener_pos, world_pos)
            except Exception:
                _log_swallow("AUDO-002", "engine.audio blanket exception fallback")
                return False
            value = bool(result)
            return (not value) if invert else value
    return False


def _normalize_path_key(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


@dataclass(frozen=True, slots=True)
class MusicPlaybackSnapshot:
    """Logical music track state for snapshot/restore across temporary overrides."""

    path: str | None
    volume: float
    loop: bool


class AudioManager:
    """Thin audio facade that caches short sounds and manages music and ambience playback.

    Three buses, each scaled by the master volume: ``music`` (the soundtrack), ``ambience`` (persistent
    environmental loops, keyed so a room loaded again doesn't start a second copy) and ``sfx`` (one-shot sounds).
    Changing a volume or muting applies at once to the music and ambience playing (nothing restarts); a one-shot
    sound effect takes its bus's level when it starts.

    Music changes are real crossfades: the new track starts while the old one fades out, both advance, and the
    old one's player is released once silent. The same track asked for again keeps playing from where it is."""

    def __init__(self) -> None:
        # The last positional sounds and how loud they played: for diagnostics and verification.
        self.recent_plays: deque[dict[str, Any]] = deque(maxlen=32)
        self._sounds: Dict[str, optional_arcade.arcade.Sound] = {}
        self._muffled_variant_cache: Dict[str, str | None] = {}
        self.master_volume: float = 1.0
        self.music_volume: float = 1.0
        self.ambience_volume: float = 1.0
        self.sfx_volume: float = 1.0
        self._muted: set[str] = set()  # "master" and/or bus names; their volumes are kept for unmuting
        self._music_track: _Track | None = None  # the music playing (or fading in)
        self._fading: list[_Track] = []  # tracks fading out (music or ambience), released once silent
        self._loops: Dict[str, _Track] = {}  # ambience loops by key
        self._unplayable: set[str] = set()  # paths that failed to load: logged once, not retried until reloaded
        self.released_players = 0  # players stopped and handed back to the backend (diagnostics)
        self.scene_music = True  # rooms set the music as they're entered (Mesh Studio's editor turns this off)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def get_sound(self, path: str) -> optional_arcade.arcade.Sound | None:
        """Return a cached Sound instance, loading it on demand."""
        sound = self._sounds.get(path)
        if sound is not None:
            return sound
        if path in self._unplayable:
            return None  # (logged once: a missing footstep would otherwise log on every step)

        try:
            resolved = resolve_path(path)
            sound = optional_arcade.arcade.Sound(resolved, streaming=False)
            self._sounds[path] = sound
            logger.debug("Loaded sound '%s'", path)
            return sound
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-003", "engine.audio blanket exception fallback")
            self._unplayable.add(path)
            logger.error("Failed to load sound '%s' (not tried again until it changes): %s", path, exc)
            return None

    def clear_cache(self) -> None:
        """Clear cached sounds and stop any music."""
        self._sounds.clear()
        self._muffled_variant_cache.clear()
        self._unplayable.clear()
        self.stop_music()
        logger.info("Cleared audio cache")

    def _muffled_variant_path(self, path: str) -> str | None:
        raw = str(path or "").strip()
        if not raw:
            return None
        suffix = Path(raw).suffix.lower()
        if suffix not in _HOT_RELOAD_AUDIO_EXTENSIONS:
            return None
        return f"{raw[: -len(suffix)]}_muffled{suffix}"

    def _muffled_variant_exists(self, muffled_path: str) -> bool:
        try:
            resolved = resolve_path(muffled_path)
        except Exception:
            _log_swallow("AUDO-004", "engine.audio blanket exception fallback")
            return False
        try:
            return Path(resolved).is_file()
        except Exception:
            _log_swallow("AUDO-005", "engine.audio blanket exception fallback")
            return False

    def _select_occluded_sound_path(self, path: str) -> str:
        original = str(path or "")
        candidate = self._muffled_variant_path(original)
        if not candidate:
            return original
        # If already cached as a sound, always prefer the variant immediately.
        if candidate in self._sounds:
            return candidate

        sentinel = object()
        cached = self._muffled_variant_cache.get(original, sentinel)
        if cached is not sentinel:
            return str(cached) if cached else original

        if self._muffled_variant_exists(candidate):
            self._muffled_variant_cache[original] = candidate
            return candidate
        self._muffled_variant_cache[original] = None
        return original

    def invalidate_muffled_variant_cache_for_path(self, changed_path: str) -> None:
        """Invalidate muffled-variant cache entries impacted by a changed audio path."""
        raw = str(changed_path or "").strip()
        if not raw:
            return
        suffix = Path(raw).suffix.lower()
        if suffix not in _HOT_RELOAD_AUDIO_EXTENSIONS:
            return

        keys_to_invalidate: set[str] = {raw}
        stem = raw[: -len(suffix)]
        if stem.endswith("_muffled"):
            keys_to_invalidate.add(f"{stem[: -len('_muffled')]}{suffix}")

        for key in keys_to_invalidate:
            self._muffled_variant_cache.pop(key, None)
            self._muffled_variant_cache.pop(key.replace("\\", "/"), None)
            self._muffled_variant_cache.pop(key.replace("/", "\\"), None)

    def reload_sound(self, path: str) -> bool:
        """Reload a cached sound entry while preserving last-good on failure."""
        key = str(path or "")
        if key not in self._sounds:
            return False
        previous_sound = self._sounds.get(key)
        try:
            resolved = resolve_path(key)
            sound = optional_arcade.arcade.Sound(resolved, streaming=False)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-006", "engine.audio blanket exception fallback")
            logger.warning("[Mesh][HotReload] audio reload failed for '%s': %s", key, exc)
            if previous_sound is not None:
                self._sounds[key] = previous_sound
            return False
        self._sounds[key] = sound
        return True

    def reload_cached_sounds(self, changed_paths: tuple[str, ...] | None) -> tuple[int, int]:
        """Best-effort reload for cached sounds affected by changed paths."""
        if not changed_paths:
            return (0, 0)

        changed_norm: set[str] = set()
        for changed in changed_paths:
            raw_path = str(changed or "").strip()
            if not raw_path:
                continue
            if Path(raw_path).suffix.lower() not in _HOT_RELOAD_AUDIO_EXTENSIONS:
                continue
            changed_norm.add(_normalize_path_key(raw_path))
            try:
                changed_norm.add(_normalize_path_key(str(resolve_path(raw_path))))
            except Exception:
                _log_swallow("AUDO-007", "engine.audio blanket exception fallback")
                pass

        if not changed_norm:
            return (0, 0)
        self._unplayable.clear()  # a track that failed to load may load now

        reloaded = 0
        failed = 0
        for key in sorted(self._sounds.keys()):
            suffix = Path(str(key)).suffix.lower()
            if suffix not in _HOT_RELOAD_AUDIO_EXTENSIONS:
                continue
            key_norm = _normalize_path_key(key)
            resolved_norm = ""
            try:
                resolved_norm = _normalize_path_key(str(resolve_path(key)))
            except Exception:
                _log_swallow("AUDO-008", "engine.audio blanket exception fallback")
                resolved_norm = ""
            if key_norm not in changed_norm and resolved_norm not in changed_norm:
                continue
            if self.reload_sound(key):
                reloaded += 1
            else:
                failed += 1
        return (reloaded, failed)

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------
    def set_master_volume(self, volume: float) -> None:
        """Adjust the global volume scalar for every bus."""
        self.master_volume = _clamp01(volume, "AUDO-009")
        self._apply_volumes()

    def set_sfx_volume(self, volume: float) -> None:
        """Adjust the volume scalar for sound effects."""
        self.sfx_volume = _clamp01(volume, "AUDO-010")

    def set_music_volume(self, volume: float) -> None:
        """Adjust the volume scalar for music."""
        self.music_volume = _clamp01(volume, "AUDO-011")
        self._apply_volumes()

    def set_ambience_volume(self, volume: float) -> None:
        """Adjust the volume scalar for ambience loops."""
        self.ambience_volume = _clamp01(volume, "AUDO-018")
        self._apply_volumes()

    def set_muted(self, muted: bool, bus: str = "master") -> None:
        """Mute or unmute everything (``"master"``) or one bus. Volumes are kept: unmuting restores them."""
        if bus != "master" and bus not in BUSES:
            raise ValueError(f"unknown audio bus {bus!r} (one of: master, {', '.join(BUSES)})")
        if muted:
            self._muted.add(bus)
        else:
            self._muted.discard(bus)
        self._apply_volumes()

    def is_muted(self, bus: str = "master") -> bool:
        return bus in self._muted

    def bus_gain(self, bus: str) -> float:
        """What a bus's sounds are multiplied by: its volume times the master volume, 0 while muted."""
        if "master" in self._muted or bus in self._muted:
            return 0.0
        return self.master_volume * float(getattr(self, f"{bus}_volume"))

    def _apply_volumes(self) -> None:
        for track in self._tracks():
            self._set_player_volume(track)

    def _set_pan(self, track: _Track, pan: float | None) -> None:
        """Pan a player as Arcade does (a position on the listener's left-right axis; a mono sound pans fully)."""
        if pan is None or (track.pan is not None and abs(pan - track.pan) < 0.005):
            return
        track.pan = max(-1.0, min(1.0, float(pan)))
        try:
            track.player.position = (track.pan, 0.0, (1.0 - track.pan * track.pan) ** 0.5)
        except Exception:  # noqa: BLE001  # REASON: audio fallback isolation (a stand-in player in tests)
            _log_swallow("AUDO-022", "engine.audio blanket exception fallback", once=True)

    def _set_player_volume(self, track: _Track) -> None:
        try:
            track.player.volume = track.volume * track.scale * self.bus_gain(track.bus)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-012", "engine.audio blanket exception fallback")
            if not getattr(self, "_mesh_music_volume_error_logged", False):
                logger.error("Failed to set %s volume: %s", track.bus, exc)
                setattr(self, "_mesh_music_volume_error_logged", True)

    def play_sound(self, path: str, volume: float = 1.0) -> None:
        sound = self.get_sound(path)
        if sound is None:
            return
        try:
            base_volume = max(0.0, min(float(volume), 1.0))
            final_volume = base_volume * self.bus_gain("sfx")
            if final_volume > 0:
                optional_arcade.arcade.play_sound(sound, volume=final_volume)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-013", "engine.audio blanket exception fallback")
            logger.error("Failed to play sound '%s': %s", path, exc)

    def play_sound_at(
        self,
        path: str,
        world_pos: tuple[float, float],
        *,
        window: Any | None = None,
        listener_pos: tuple[float, float] | None = None,
        base_volume: float = 1.0,
        max_dist: float = 800.0,
        rolloff: str = "linear",
        pan: bool = True,
    ) -> None:
        """Play a sound with distance attenuation and optional stereo pan.

        This is additive and does not alter existing flat `play_sound` behavior.
        If `listener_pos` is not provided (or invalid), playback falls back to
        base volume semantics without spatial attenuation.
        """
        base = max(0.0, min(float(base_volume), 1.0))
        final_volume = base * self.bus_gain("sfx")

        world_xy = _as_xy(world_pos)
        listener_xy = _as_xy(listener_pos) if listener_pos is not None else None
        if listener_xy is None and window is not None:
            listener_xy = _resolve_listener_pos(window)
        pan_value = 0.0
        is_occluded = False
        if world_xy is not None and listener_xy is not None:
            dx = float(world_xy[0] - listener_xy[0])
            dy = float(world_xy[1] - listener_xy[1])
            distance = hypot(dx, dy)
            gain = _attenuate(distance, max_dist=max_dist, rolloff=rolloff)
            is_occluded = bool(window is not None and _is_occluded(window, listener_xy, world_xy))
            if is_occluded:
                gain *= float(WORLD_SFX_OCCLUDED_VOLUME_MUL)
            final_volume *= gain
            if pan:
                md = max(1e-9, float(max_dist))
                pan_value = _pan(dx / md, max_pan=1.0)
                if is_occluded:
                    pan_value *= float(WORLD_SFX_OCCLUDED_PAN_MUL)

        self.recent_plays.append({"path": path, "volume": round(final_volume, 4), "pan": round(pan_value, 4),
                                  "distance": round(hypot(dx, dy), 1) if world_xy and listener_xy else None,
                                  "occluded": is_occluded})
        if final_volume <= 0.0:
            return
        sound_path = self._select_occluded_sound_path(path) if is_occluded else path
        sound = self.get_sound(sound_path)
        if sound is None and sound_path != path:
            sound = self.get_sound(path)
        if sound is None:
            return
        try:
            if pan and world_xy is not None and listener_xy is not None:
                optional_arcade.arcade.play_sound(sound, volume=final_volume, pan=pan_value)
            else:
                optional_arcade.arcade.play_sound(sound, volume=final_volume)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-014", "engine.audio blanket exception fallback")
            logger.error("Failed to play spatial sound '%s': %s", path, exc)

    def play_world_sfx(
        self,
        path: str,
        world_pos: tuple[float, float],
        *,
        window: Any,
        base_volume: float = 1.0,
        profile: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Play world-positioned SFX with standardized spatial defaults."""
        spatial_kwargs: Dict[str, Any] = {
            "max_dist": 800.0,
            "rolloff": "linear",
            "pan": True,
        }
        if profile is not None:
            profile_overrides = WORLD_SFX_PROFILES.get(str(profile))
            if isinstance(profile_overrides, dict):
                spatial_kwargs.update(profile_overrides)
        if kwargs:
            spatial_kwargs.update(kwargs)

        self.play_sound_at(
            path,
            world_pos=world_pos,
            window=window,
            listener_pos=None,
            base_volume=base_volume,
            max_dist=float(spatial_kwargs.get("max_dist", 800.0)),
            rolloff=str(spatial_kwargs.get("rolloff", "linear")),
            pan=bool(spatial_kwargs.get("pan", True)),
        )

    # ------------------------------------------------------------------
    # Music
    # ------------------------------------------------------------------
    @property
    def music_path(self) -> str | None:
        """The track playing or fading in (None: no music, or fading to silence)."""
        return self._music_track.path if self._music_track is not None else None

    def play_music(self, path: str, volume: float = 1.0, loop: bool = True) -> None:
        """Play ``path`` from its start at once (anything playing stops; no fade)."""
        self.stop_music()
        self.transition_music(path, fade_out_s=0.0, fade_in_s=0.0, volume=volume, loop=loop)

    def snapshot_music(self) -> MusicPlaybackSnapshot:
        track = self._music_track
        if track is None:
            return MusicPlaybackSnapshot(path=None, volume=0.0, loop=False)
        return MusicPlaybackSnapshot(path=track.path, volume=float(track.volume), loop=bool(track.loop))

    def restore_music(
        self,
        snapshot: MusicPlaybackSnapshot,
        *,
        fade_out_s: float = 0.25,
        fade_in_s: float = 0.25,
    ) -> None:
        self.transition_music(snapshot.path or "", fade_out_s=fade_out_s, fade_in_s=fade_in_s,
                              volume=snapshot.volume if snapshot.path else 0.0, loop=snapshot.loop)

    def transition_music(
        self,
        path: str,
        *,
        fade_out_s: float = 0.25,
        fade_in_s: float = 0.25,
        volume: float = 1.0,
        loop: bool = True,
    ) -> None:
        """Change the music to ``path`` (empty: silence), crossfading: the playing track fades out over
        ``fade_out_s`` while the new one starts and fades in over ``fade_in_s``, both playing meanwhile.

        - The track already playing (or fading in): it keeps playing, its volume eased to ``volume``.
        - A track still fading out (straight back through a door): it fades back in from there, not restarted.
        - A track that can't be loaded: logged once, and the music playing carries on."""
        target = str(path or "").strip()
        level = _clamp01(volume, "AUDO-019")
        current = self._music_track
        if target and current is not None and current.path == target:
            current.volume, current.loop = level, bool(loop)
            _set_loop(current.player, loop)
            current.fade_to(1.0, fade_in_s)
            self._set_player_volume(current)
            return
        incoming = next((t for t in self._fading if t.bus == "music" and t.path == target), None) if target else None
        if incoming is not None:
            self._fading.remove(incoming)
            incoming.volume, incoming.loop = level, bool(loop)
            _set_loop(incoming.player, loop)
        elif target:
            incoming = self._start(target, "music", level, loop)
            if incoming is None:
                return  # (logged) the music playing carries on
            incoming.scale = 0.0
        if current is not None:
            current.fade_to(0.0, fade_out_s)
            self._fading.append(current)
        self._music_track = incoming
        if incoming is not None:
            incoming.fade_to(1.0, fade_in_s)
        self._settle()

    def update(self, dt: float) -> None:
        """Advance fades (call every frame, paused or not) and release tracks that have faded out."""
        if self._music_track is None and not self._fading and not self._loops:
            return
        dt = max(0.0, float(dt))
        for track in self._tracks():
            track.advance(dt)
        self._settle()

    def stop_music(self) -> None:
        """Stop all music at once (the playing track and any fading out), releasing their players."""
        if self._music_track is not None:
            self._release(self._music_track)
            self._music_track = None
        for track in [t for t in self._fading if t.bus == "music"]:
            self._fading.remove(track)
            self._release(track)

    # ------------------------------------------------------------------
    # Ambience (persistent loops; Milestone 21B's emitters build on these)
    # ------------------------------------------------------------------
    def play_loop(self, key: str, path: str, *, volume: float = 1.0, fade_in_s: float = 0.0, pan: float | None = None,
                  loop: bool = True) -> bool:
        """Keep the ambience loop ``key`` playing ``path`` at ``volume``. Asked again with the same path (a room
        loaded again, or a sound emitter every frame as the listener moves), it keeps playing: only its volume and
        ``pan`` change (a fade under way carries on), never a second copy. One still fading out after ``stop_loop``
        fades back in from where it is. Another path crossfades to it. ``pan``: -1 (left) to 1 (right); None leaves
        it as it is (centred to start). ``loop`` False: it plays once. False if the file can't be played."""
        level = _clamp01(volume, "AUDO-020")
        current = self._loops.get(key)
        if current is not None and current.path == path:
            current.volume = level
            self._set_pan(current, pan)
            self._set_player_volume(current)
            return True
        track = next((t for t in self._fading if t.bus == "ambience" and t.key == key and t.path == path), None)
        if track is not None:  # back in range before it had faded away
            self._fading.remove(track)
            track.volume = level
        else:
            track = self._start(path, "ambience", level, loop)
            if track is None:
                return False
            track.key, track.scale = key, 0.0
        track.fade_to(1.0, fade_in_s)
        self._set_pan(track, pan)
        if current is not None:
            current.fade_to(0.0, fade_in_s)
            self._fading.append(current)
        self._loops[key] = track
        self._settle()
        return True

    def stop_loop(self, key: str, *, fade_out_s: float = 0.0) -> None:
        track = self._loops.pop(key, None)
        if track is not None:
            track.fade_to(0.0, fade_out_s)
            self._fading.append(track)
            self._settle()

    def loops(self) -> dict[str, str]:
        """The ambience loops playing: key -> path."""
        return {key: track.path for key, track in self._loops.items()}

    # ------------------------------------------------------------------
    # Lifecycle and diagnostics
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Stop everything and release every player (the game is closing)."""
        self.stop_music()
        for track in [*self._loops.values(), *self._fading]:
            self._release(track)
        self._loops.clear()
        self._fading.clear()

    def diagnostics(self) -> dict[str, Any]:
        return {"music": self.music_path, "fading_out": [t.path for t in self._fading], "loops": self.loops(),
                "live_players": len(self._tracks()), "released_players": self.released_players,
                "volumes": {"master": self.master_volume, **{b: getattr(self, f"{b}_volume") for b in BUSES}},
                "muted": sorted(self._muted), "unplayable": sorted(self._unplayable)}

    def _tracks(self) -> list[_Track]:
        return [*([self._music_track] if self._music_track is not None else []), *self._loops.values(), *self._fading]

    def _settle(self) -> None:
        """Apply fades to players; release tracks faded out, and the oldest beyond ``MAX_FADING_TRACKS``."""
        for track in [t for t in self._fading if t.scale <= 0.0]:
            self._fading.remove(track)
            self._release(track)
        while len(self._fading) > MAX_FADING_TRACKS:
            self._release(self._fading.pop(0))
        self._apply_volumes()

    def _start(self, path: str, bus: str, volume: float, loop: bool) -> _Track | None:
        if path in self._unplayable:
            return None
        try:
            sound = optional_arcade.arcade.Sound(resolve_path(path), streaming=True)
            player = sound.play(volume=0.0, loop=loop)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-016", "engine.audio blanket exception fallback")
            self._unplayable.add(path)
            logger.error("Can't play %s '%s' (not tried again until it changes): %s", bus, path, exc)
            return None
        logger.info("Playing %s '%s' (loop=%s)", bus, path, loop)
        return _Track(path=path, bus=bus, player=player, volume=volume, loop=bool(loop))

    def _release(self, track: _Track) -> None:
        try:
            optional_arcade.arcade.stop_sound(track.player)  # pause, delete, and drop arcade's reference
        except Exception:  # noqa: BLE001  # REASON: audio fallback isolation (a stand-in player in tests)
            _log_swallow("AUDO-015", "engine.audio blanket exception fallback", once=True)
            try:
                track.player.pause()
            except Exception:  # noqa: BLE001  # REASON: audio fallback isolation
                _log_swallow("AUDO-017", "engine.audio blanket exception fallback", once=True)
        self.released_players += 1
        logger.debug("Stopped %s '%s'", track.bus, track.path)


def _clamp01(value: Any, code: str) -> float:
    try:
        number = float(value)
    except Exception:
        _log_swallow(code, "engine.audio blanket exception fallback")
        return 1.0
    return max(0.0, min(number, 1.0)) if number == number else 1.0


def _set_loop(player: Any, loop: bool) -> None:
    try:
        player.loop = bool(loop)
    except Exception:  # noqa: BLE001  # REASON: audio fallback isolation
        _log_swallow("AUDO-021", "engine.audio blanket exception fallback", once=True)


@dataclass
class _Track:
    """One streamed playback (a music track, an ambience loop): its player, its own volume, and its fade."""

    path: str
    bus: str
    player: Any
    volume: float  # its own volume (a room's music_volume), before the bus and master
    loop: bool
    key: str = ""  # an ambience loop's key
    pan: float | None = None  # -1 left .. 1 right; None: never set (centred)
    scale: float = 1.0  # where its fade is, 0..1
    start: float = 1.0
    target: float = 1.0
    duration: float = 0.0
    elapsed: float = 0.0

    def fade_to(self, target: float, seconds: float) -> None:
        self.start, self.target, self.elapsed = self.scale, target, 0.0
        self.duration = max(0.0, float(seconds))
        if self.duration <= 0.0:
            self.scale = target

    def advance(self, dt: float) -> None:
        if self.scale == self.target:
            return
        self.elapsed += dt
        progress = 1.0 if self.duration <= 0.0 else min(1.0, self.elapsed / self.duration)
        self.scale = self.start + (self.target - self.start) * progress
