"""Audio caching and playback helpers for Mesh Engine."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from pathlib import Path
from typing import Any, Dict, Optional

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


class AudioManager:
    """Thin audio facade that caches short sounds and manages music playback."""

    def __init__(self) -> None:
        self._sounds: Dict[str, optional_arcade.arcade.Sound] = {}
        self._muffled_variant_cache: Dict[str, str | None] = {}
        self._music: Optional[optional_arcade.arcade.Sound] = None
        self._music_player: Optional[Any] = None
        self.master_volume: float = 1.0
        self.sfx_volume: float = 1.0
        self.music_volume: float = 1.0
        self._music_base_volume: float = 1.0
        self._music_transition: _MusicTransition | None = None
        self._music_transition_scale: float = 1.0

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def get_sound(self, path: str) -> optional_arcade.arcade.Sound | None:
        """Return a cached Sound instance, loading it on demand."""
        sound = self._sounds.get(path)
        if sound is not None:
            return sound

        try:
            resolved = resolve_path(path)
            sound = optional_arcade.arcade.Sound(resolved, streaming=False)
            self._sounds[path] = sound
            logger.debug("Loaded sound '%s'", path)
            return sound
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-003", "engine.audio blanket exception fallback")
            logger.error("Failed to load sound '%s': %s", path, exc)
            return None

    def clear_cache(self) -> None:
        """Clear cached sounds and stop any music."""
        self._sounds.clear()
        self._muffled_variant_cache.clear()
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
        """Adjust the global volume scalar for both sounds and music."""
        try:
            value = float(volume)
        except Exception:
            _log_swallow("AUDO-009", "engine.audio blanket exception fallback")
            value = 1.0
        self.master_volume = max(0.0, min(value, 1.0))
        self._update_music_volume()

    def set_sfx_volume(self, volume: float) -> None:
        """Adjust the volume scalar for sound effects."""
        try:
            value = float(volume)
        except Exception:
            _log_swallow("AUDO-010", "engine.audio blanket exception fallback")
            value = 1.0
        self.sfx_volume = max(0.0, min(value, 1.0))

    def set_music_volume(self, volume: float) -> None:
        """Adjust the volume scalar for music."""
        try:
            value = float(volume)
        except Exception:
            _log_swallow("AUDO-011", "engine.audio blanket exception fallback")
            value = 1.0
        self.music_volume = max(0.0, min(value, 1.0))
        self._update_music_volume()

    def _update_music_volume(self) -> None:
        if self._music_player is not None:
            try:
                # Final volume = track_base * music_category * master
                final = (
                    self._music_base_volume
                    * self.music_volume
                    * self.master_volume
                    * self._music_transition_scale
                )
                self._music_player.volume = final
            except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
                _log_swallow("AUDO-012", "engine.audio blanket exception fallback")
                if not getattr(self, "_mesh_music_volume_error_logged", False):
                    logger.error("Failed to set music volume: %s", exc)
                    setattr(self, "_mesh_music_volume_error_logged", True)

    def play_sound(self, path: str, volume: float = 1.0) -> None:
        sound = self.get_sound(path)
        if sound is None:
            return
        try:
            base_volume = max(0.0, min(float(volume), 1.0))
            final_volume = base_volume * self.sfx_volume * self.master_volume
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
        final_volume = base * self.sfx_volume * self.master_volume

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

    def play_music(self, path: str, volume: float = 1.0, loop: bool = True) -> None:
        self.stop_music()
        self._music_transition = None
        self._music_transition_scale = 1.0
        self._play_music_internal(path, volume=volume, loop=loop, start_volume_scale=1.0)

    def transition_music(
        self,
        path: str,
        *,
        fade_out_s: float = 0.25,
        fade_in_s: float = 0.25,
        volume: float = 1.0,
        loop: bool = True,
    ) -> None:
        target_path = str(path or "").strip()
        fade_out = max(0.0, float(fade_out_s))
        fade_in = max(0.0, float(fade_in_s))
        target_volume = max(0.0, min(float(volume), 1.0))
        if not target_path and self._music_player is None:
            return

        if self._music_player is None:
            if not target_path:
                return
            self._music_transition = _MusicTransition(
                phase="in",
                timer=0.0,
                fade_out=0.0,
                fade_in=fade_in,
                target_path=None,
                target_volume=target_volume,
                loop=loop,
            )
            self._music_transition_scale = 0.0
            self._play_music_internal(target_path, volume=target_volume, loop=loop, start_volume_scale=0.0)
            return

        self._music_transition = _MusicTransition(
            phase="out",
            timer=0.0,
            fade_out=fade_out,
            fade_in=fade_in,
            target_path=target_path or None,
            target_volume=target_volume,
            loop=loop,
        )

    def update(self, dt: float) -> None:
        transition = self._music_transition
        if transition is None:
            return
        dt = max(0.0, float(dt))
        if transition.phase == "out":
            if transition.fade_out <= 0.0:
                done = True
            else:
                transition.timer += dt
                progress = min(1.0, transition.timer / transition.fade_out)
                self._music_transition_scale = 1.0 - progress
                self._update_music_volume()
                done = progress >= 1.0
            if done:
                self._stop_music_internal(clear_transition=False)
                if transition.target_path:
                    transition.phase = "in"
                    transition.timer = 0.0
                    self._music_transition_scale = 0.0
                    self._play_music_internal(
                        transition.target_path,
                        volume=transition.target_volume,
                        loop=transition.loop,
                        start_volume_scale=0.0,
                    )
                else:
                    self._music_transition = None
                    self._music_transition_scale = 1.0
            return

        if transition.phase == "in":
            if transition.fade_in <= 0.0:
                done = True
            else:
                transition.timer += dt
                progress = min(1.0, transition.timer / transition.fade_in)
                self._music_transition_scale = progress
                self._update_music_volume()
                done = progress >= 1.0
            if done:
                self._music_transition = None
                self._music_transition_scale = 1.0
                self._update_music_volume()

    def stop_music(self) -> None:
        self._stop_music_internal(clear_transition=True)

    def _stop_music_internal(self, *, clear_transition: bool) -> None:
        if self._music_player is not None:
            try:
                self._music_player.pause()
            except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
                _log_swallow("AUDO-015", "engine.audio blanket exception fallback")
                if not getattr(self, "_mesh_music_stop_error_logged", False):
                    logger.error("Failed to stop music: %s", exc)
                    setattr(self, "_mesh_music_stop_error_logged", True)
        if self._music_player is not None or self._music is not None:
            logger.info("Stopped music")
        self._music_player = None
        self._music = None
        self._music_base_volume = 1.0
        if clear_transition:
            self._music_transition = None
            self._music_transition_scale = 1.0

    def _play_music_internal(self, path: str, *, volume: float, loop: bool, start_volume_scale: float) -> None:
        try:
            resolved = resolve_path(path)
            music = optional_arcade.arcade.Sound(resolved, streaming=True)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-016", "engine.audio blanket exception fallback")
            logger.error("Failed to load music '%s': %s", path, exc)
            return

        self._music = music
        self._music_base_volume = max(0.0, min(float(volume), 1.0))
        self._music_transition_scale = max(0.0, min(float(start_volume_scale), 1.0))
        try:
            final_volume = (
                self._music_base_volume
                * self.music_volume
                * self.master_volume
                * self._music_transition_scale
            )
            self._music_player = music.play(volume=final_volume, loop=loop)
            logger.info("Playing music '%s' (loop=%s)", path, loop)
        except Exception as exc:  # noqa: BLE001  # REASON: audio fallback isolation
            _log_swallow("AUDO-017", "engine.audio blanket exception fallback")
            logger.error("Failed to play music '%s': %s", path, exc)
            self._music = None
            self._music_player = None


@dataclass
class _MusicTransition:
    phase: str
    timer: float
    fade_out: float
    fade_in: float
    target_path: str | None
    target_volume: float
    loop: bool
