"""Audio caching and playback helpers for Mesh Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import engine.optional_arcade as optional_arcade

from .logging_tools import get_logger
from .paths import resolve_path

logger = get_logger(__name__)


class AudioManager:
    """Thin audio facade that caches short sounds and manages music playback."""

    def __init__(self) -> None:
        self._sounds: Dict[str, optional_arcade.arcade.Sound] = {}
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
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load sound '%s': %s", path, exc)
            return None

    def clear_cache(self) -> None:
        """Clear cached sounds and stop any music."""
        self._sounds.clear()
        self.stop_music()
        logger.info("Cleared audio cache")

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------
    def set_master_volume(self, volume: float) -> None:
        """Adjust the global volume scalar for both sounds and music."""
        try:
            value = float(volume)
        except Exception:
            value = 1.0
        self.master_volume = max(0.0, min(value, 1.0))
        self._update_music_volume()

    def set_sfx_volume(self, volume: float) -> None:
        """Adjust the volume scalar for sound effects."""
        try:
            value = float(volume)
        except Exception:
            value = 1.0
        self.sfx_volume = max(0.0, min(value, 1.0))

    def set_music_volume(self, volume: float) -> None:
        """Adjust the volume scalar for music."""
        try:
            value = float(volume)
        except Exception:
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
            except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to play sound '%s': %s", path, exc)

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
            except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
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
        except Exception as exc:  # noqa: BLE001
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
