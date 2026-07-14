"""Battle-specific audio playback: semantic cue mapping and ordered dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from engine.audio import MusicPlaybackSnapshot
from engine.logging_tools import get_logger

from .battle_sound_cues import (
    APPROVED_BATTLE_SOUND_CUES,
    BATTLE_ACTION,
    BATTLE_CAPTURE_FAIL,
    BATTLE_CAPTURE_SUCCESS,
    BATTLE_CAPTURE_THROW,
    BATTLE_COMPANION_PRAISE,
    BATTLE_COMPANION_SCOLD,
    BATTLE_COMPANION_WAIT,
    BATTLE_DEFEAT,
    BATTLE_FAINT,
    BATTLE_HIT,
    BATTLE_RESISTED,
    BATTLE_START,
    BATTLE_SUPER_EFFECTIVE,
    BATTLE_SWITCH,
    BATTLE_VICTORY,
)

logger = get_logger(__name__)

BATTLE_CUE_INTERVAL_S = 0.10

BATTLE_MUSIC_PATH = "assets/music/dungeon_theme.wav"
BATTLE_MUSIC_VOLUME = 0.7
BATTLE_MUSIC_LOOP = True
BATTLE_MUSIC_FADE_OUT_S = 0.25
BATTLE_MUSIC_FADE_IN_S = 0.25
MUSIC_RESTORE_FADE_OUT_S = 0.25
MUSIC_RESTORE_FADE_IN_S = 0.25


@dataclass(frozen=True, slots=True)
class BattleSoundSpec:
    path: str
    volume: float = 1.0


DEFAULT_BATTLE_SOUND_MAP: dict[str, BattleSoundSpec] = {
    BATTLE_START: BattleSoundSpec("assets/sounds/ui_open.wav", volume=0.85),
    BATTLE_ACTION: BattleSoundSpec("assets/sounds/attack.wav", volume=0.9),
    BATTLE_HIT: BattleSoundSpec("assets/sounds/hit.wav", volume=0.95),
    BATTLE_RESISTED: BattleSoundSpec("assets/sounds/ui_close.wav", volume=0.75),
    BATTLE_SUPER_EFFECTIVE: BattleSoundSpec("assets/sounds/ui_open.wav", volume=0.85),
    BATTLE_SWITCH: BattleSoundSpec("assets/sounds/ui_open.wav", volume=0.8),
    BATTLE_CAPTURE_THROW: BattleSoundSpec("assets/sounds/attack.wav", volume=0.85),
    BATTLE_CAPTURE_FAIL: BattleSoundSpec("assets/sounds/ui_close.wav", volume=0.8),
    BATTLE_CAPTURE_SUCCESS: BattleSoundSpec("assets/sounds/ui_open.wav", volume=0.9),
    BATTLE_FAINT: BattleSoundSpec("assets/sounds/die.wav", volume=0.95),
    BATTLE_VICTORY: BattleSoundSpec("assets/sounds/ui_open.wav", volume=0.9),
    BATTLE_DEFEAT: BattleSoundSpec("assets/sounds/die.wav", volume=0.9),
    BATTLE_COMPANION_PRAISE: BattleSoundSpec("assets/sounds/ui_click.wav", volume=0.8),
    BATTLE_COMPANION_SCOLD: BattleSoundSpec("assets/sounds/ui_close.wav", volume=0.75),
    BATTLE_COMPANION_WAIT: BattleSoundSpec("assets/sounds/ui_hover.wav", volume=0.7),
}


class BattleAudioPlayback:
    """Ordered battle cue playback and temporary battle music for one encounter."""

    def __init__(
        self,
        *,
        sound_map: Mapping[str, BattleSoundSpec] | None = None,
        cue_interval_s: float = BATTLE_CUE_INTERVAL_S,
    ) -> None:
        self._sound_map = dict(sound_map) if sound_map is not None else dict(DEFAULT_BATTLE_SOUND_MAP)
        self._cue_interval_s = max(0.0, float(cue_interval_s))
        self._audio: Any | None = None
        self._pending_cues: list[str] = []
        self._cue_elapsed = 0.0
        self._intro_consumed = False
        self._music_snapshot: MusicPlaybackSnapshot | None = None
        self._battle_started = False
        self._music_override_active = False
        self._music_restored = False

    def attach(self, audio: Any | None) -> None:
        self._audio = audio

    def begin_battle(self) -> None:
        if self._battle_started:
            return
        self._battle_started = True
        audio = self._audio
        if audio is None:
            return

        snapshot_fn = getattr(audio, "snapshot_music", None)
        transition_fn = getattr(audio, "transition_music", None)
        restore_fn = getattr(audio, "restore_music", None)
        if not callable(snapshot_fn) or not callable(transition_fn) or not callable(restore_fn):
            logger.debug("Battle music handoff unsupported: missing audio seam methods")
            return

        try:
            self._music_snapshot = snapshot_fn()
        except Exception as exc:  # noqa: BLE001  # REASON: battle entry must survive audio failures
            logger.debug("Battle music snapshot failed: %s", exc)
            self._music_snapshot = None
            return

        try:
            transition_fn(
                BATTLE_MUSIC_PATH,
                fade_out_s=BATTLE_MUSIC_FADE_OUT_S,
                fade_in_s=BATTLE_MUSIC_FADE_IN_S,
                volume=BATTLE_MUSIC_VOLUME,
                loop=BATTLE_MUSIC_LOOP,
            )
        except Exception as exc:  # noqa: BLE001  # REASON: battle entry must survive audio failures
            logger.debug("Battle music start failed: %s", exc)
            self._music_snapshot = None
            return

        self._music_override_active = True

    def consume_intro(self, cue: str | None) -> None:
        if cue is None or self._intro_consumed:
            return
        self._intro_consumed = True
        self._dispatch_cues((cue,))

    def dispatch_step_cues(self, cues: tuple[str, ...]) -> None:
        self._pending_cues.clear()
        self._cue_elapsed = 0.0
        self._dispatch_cues(cues)

    def update(self, dt: float) -> None:
        if not self._pending_cues:
            return
        self._cue_elapsed += max(0.0, float(dt))
        interval = self._cue_interval_s
        if interval <= 0.0:
            while self._pending_cues:
                self._play_cue(self._pending_cues.pop(0))
            return
        while self._pending_cues and self._cue_elapsed >= interval:
            self._cue_elapsed -= interval
            self._play_cue(self._pending_cues.pop(0))

    def end_battle(self) -> None:
        self._pending_cues.clear()
        self._cue_elapsed = 0.0
        self._restore_music_once()

    def _dispatch_cues(self, cues: tuple[str, ...]) -> None:
        if not cues:
            return
        self._play_cue(cues[0])
        if len(cues) > 1:
            self._pending_cues = list(cues[1:])
            self._cue_elapsed = 0.0

    def _play_cue(self, cue: str) -> None:
        spec = self._sound_map.get(str(cue))
        if spec is None:
            logger.debug("Ignoring unmapped battle audio cue: %s", cue)
            return
        audio = self._audio
        if audio is None:
            return
        play_sound = getattr(audio, "play_sound", None)
        if not callable(play_sound):
            return
        try:
            play_sound(spec.path, volume=spec.volume)
        except Exception as exc:  # noqa: BLE001  # REASON: cue playback must not affect battle flow
            logger.debug("Battle cue playback failed for %s: %s", cue, exc)

    def _restore_music_once(self) -> None:
        if self._music_restored or not self._music_override_active:
            return
        self._music_restored = True
        snapshot = self._music_snapshot
        self._music_snapshot = None
        self._music_override_active = False
        audio = self._audio
        if audio is None or snapshot is None:
            return
        restore = getattr(audio, "restore_music", None)
        if not callable(restore):
            return
        try:
            restore(
                snapshot,
                fade_out_s=MUSIC_RESTORE_FADE_OUT_S,
                fade_in_s=MUSIC_RESTORE_FADE_IN_S,
            )
        except Exception as exc:  # noqa: BLE001  # REASON: teardown must survive audio failures
            logger.debug("Battle music restore failed: %s", exc)


def approved_battle_sound_map_keys() -> frozenset[str]:
    return frozenset(DEFAULT_BATTLE_SOUND_MAP.keys())


def approved_battle_sound_map_matches_vocabulary() -> bool:
    return approved_battle_sound_map_keys() == frozenset(APPROVED_BATTLE_SOUND_CUES)


def default_battle_audio_asset_paths() -> tuple[str, ...]:
    paths = {spec.path for spec in DEFAULT_BATTLE_SOUND_MAP.values()}
    paths.add(BATTLE_MUSIC_PATH)
    return tuple(sorted(paths))
