"""Semantic battle sound-cue vocabulary for presentation steps.

Pure module: no asset paths, audio playback, or GameWindow dependencies.
"""

from __future__ import annotations

from typing import Final

BATTLE_START: Final = "battle.start"
BATTLE_ACTION: Final = "battle.action"
BATTLE_HIT: Final = "battle.hit"
BATTLE_RESISTED: Final = "battle.resisted"
BATTLE_SUPER_EFFECTIVE: Final = "battle.super_effective"
BATTLE_SWITCH: Final = "battle.switch"
BATTLE_CAPTURE_THROW: Final = "battle.capture_throw"
BATTLE_CAPTURE_FAIL: Final = "battle.capture_fail"
BATTLE_CAPTURE_SUCCESS: Final = "battle.capture_success"
BATTLE_FAINT: Final = "battle.faint"
BATTLE_VICTORY: Final = "battle.victory"
BATTLE_DEFEAT: Final = "battle.defeat"
BATTLE_COMPANION_PRAISE: Final = "battle.companion_praise"
BATTLE_COMPANION_SCOLD: Final = "battle.companion_scold"
BATTLE_COMPANION_WAIT: Final = "battle.companion_wait"

APPROVED_BATTLE_SOUND_CUES: tuple[str, ...] = (
    BATTLE_START,
    BATTLE_ACTION,
    BATTLE_HIT,
    BATTLE_RESISTED,
    BATTLE_SUPER_EFFECTIVE,
    BATTLE_SWITCH,
    BATTLE_CAPTURE_THROW,
    BATTLE_CAPTURE_FAIL,
    BATTLE_CAPTURE_SUCCESS,
    BATTLE_FAINT,
    BATTLE_VICTORY,
    BATTLE_DEFEAT,
    BATTLE_COMPANION_PRAISE,
    BATTLE_COMPANION_SCOLD,
    BATTLE_COMPANION_WAIT,
)

KNOWN_BATTLE_SOUND_CUES: frozenset[str] = frozenset(APPROVED_BATTLE_SOUND_CUES)


def effectiveness_audio_cue(multiplier: float) -> str | None:
    if multiplier > 1.0:
        return BATTLE_SUPER_EFFECTIVE
    if multiplier < 1.0:
        return BATTLE_RESISTED
    return None


def move_resolution_audio_cues(*, hit: bool, type_multiplier: float) -> tuple[str, ...]:
    if not hit:
        return (BATTLE_ACTION,)
    cues: list[str] = [BATTLE_ACTION, BATTLE_HIT]
    effectiveness = effectiveness_audio_cue(type_multiplier)
    if effectiveness is not None:
        cues.append(effectiveness)
    return tuple(cues)


def faint_step_audio_cues() -> tuple[str, ...]:
    return (BATTLE_FAINT,)


def capture_attempt_audio_cues(*, caught: bool) -> tuple[str, ...]:
    if caught:
        return (BATTLE_CAPTURE_THROW, BATTLE_CAPTURE_SUCCESS)
    return (BATTLE_CAPTURE_THROW, BATTLE_CAPTURE_FAIL)
