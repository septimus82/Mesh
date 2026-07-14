"""Semantic battle sound-cue vocabulary for presentation steps.

Pure module: no asset paths, audio playback, or GameWindow dependencies.
"""

from __future__ import annotations

from typing import Final, Sequence

from .battle_model import Move, TypeChart, type_multiplier

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

KNOWN_BATTLE_SOUND_CUES: frozenset[str] = frozenset(
    {
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
    }
)


def effectiveness_audio_cue(multiplier: float) -> str | None:
    if multiplier > 1.0:
        return BATTLE_SUPER_EFFECTIVE
    if multiplier < 1.0:
        return BATTLE_RESISTED
    return None


def move_resolution_audio_cue(
    *,
    hit: bool,
    move: Move | None,
    defender_types: Sequence[str],
    type_chart: TypeChart | None,
) -> str:
    if not hit:
        return BATTLE_ACTION
    if move is not None:
        multiplier = type_multiplier(move.type, defender_types, type_chart)
        effectiveness = effectiveness_audio_cue(multiplier)
        if effectiveness is not None:
            return effectiveness
    return BATTLE_HIT


def faint_presentation_audio_cue(
    *,
    player_clip: str | None,
    opponent_clip: str | None,
) -> str | None:
    if player_clip == "victory":
        return BATTLE_VICTORY
    if player_clip == "faint" or opponent_clip == "faint":
        return BATTLE_FAINT
    return None
