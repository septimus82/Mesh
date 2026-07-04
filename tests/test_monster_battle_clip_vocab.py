"""Battle clip vocabulary, loader validation, and presentation trigger wiring."""

from __future__ import annotations

import random
import types
from dataclasses import replace
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import (
    BattlePresentationStep,
    MonsterBattleMode,
    _build_companion_reinforcement_steps,
)
from engine.monster.battle_model import BattleSprite, BattleSpriteClip, BattleStats, MonsterInstance, Move, Species
from engine.monster.battle_sprite_view import BattleSpriteAnimator
from engine.monster.battle_terms import DEFAULT_BATTLE_TERMS
from engine.monster.companion_mind import FLEE, CompanionMind, DecisionContext, DecisionResult, LearnedWeights, Temperament
from engine.monster.data_load import KNOWN_BATTLE_CLIP_NAMES, parse_species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)

PLAYER = Species(
    id="player_mon",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("tackle", "ko"),
)
OPPONENT = Species(
    id="opponent_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("normal",),
    learnset=("tackle",),
)
FAST_OPPONENT = Species(
    id="fast_opponent",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=50),
    types=("normal",),
    learnset=("tackle",),
)
HARD_CATCH = Species(
    id="hard_catch",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
    capture_rate=10,
)


def _species_payload(*, extra_clips: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    clips: dict[str, Any] = {
        "idle": {"frames": [0], "fps": 6, "loop": True},
        "attack": {"frames": [1], "fps": 8, "loop": False},
        "defend": {"frames": [2], "fps": 8, "loop": False},
        "hurt": {"frames": [3], "fps": 4, "loop": False},
        "faint": {"frames": [4], "fps": 6, "loop": False},
    }
    if extra_clips:
        clips.update(extra_clips)
    return {
        "species": [
            {
                "id": "demo",
                "types": ["normal"],
                "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                "learnset": ["tackle"],
                "battle_sprite": {
                    "sheet": "assets/sprites/demo.png",
                    "columns": 4,
                    "rows": 2,
                    "frame_width": 32,
                    "frame_height": 32,
                    "clips": clips,
                },
            }
        ]
    }


@pytest.mark.parametrize(
    "clip_name",
    sorted({"cheer", "cower", "flee", "victory", "capture", "status"}),
)
def test_loader_accepts_companion_era_clip_names(clip_name: str) -> None:
    payload = _species_payload(extra_clips={clip_name: {"frames": [5], "fps": 6, "loop": True}})
    species, result = parse_species(payload)
    assert result.ok is True
    sprite = species["demo"].battle_sprite
    assert sprite is not None
    assert clip_name in sprite.clips


def test_loader_rejects_unknown_clip_with_full_allowed_list() -> None:
    payload = _species_payload(extra_clips={"dance": {"frames": [5], "fps": 6, "loop": True}})
    _, result = parse_species(payload)
    assert result.ok is False
    message = " ".join(result.errors)
    assert "unknown clip 'dance'" in message
    for name in sorted(KNOWN_BATTLE_CLIP_NAMES):
        assert name in message


def test_legacy_five_clip_species_config_loads_unchanged() -> None:
    payload = {
        "species": [
            {
                "id": "legacy",
                "types": ["grass"],
                "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                "learnset": ["tackle"],
                "battle_sprite": {
                    "sheet": "assets/sprites/legacy.png",
                    "columns": 3,
                    "rows": 1,
                    "frame_width": 16,
                    "frame_height": 16,
                    "clips": {
                        "idle": {"frames": [0, 1], "fps": 6, "loop": True},
                        "attack": {"frames": [2], "fps": 8, "loop": False},
                        "defend": {"frames": [2], "fps": 8, "loop": False},
                        "hurt": {"frames": [2], "fps": 4, "loop": False},
                        "faint": {"frames": [2], "fps": 6, "loop": False},
                    },
                },
            }
        ]
    }
    species, result = parse_species(payload)
    assert result.ok is True
    clips = species["legacy"].battle_sprite.clips  # type: ignore[union-attr]
    assert set(clips) == {"idle", "attack", "defend", "hurt", "faint"}


def _window(*, values: dict[str, Any] | None = None) -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = UIController(as_any(window))
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    from engine.game_state_controller import GameState

    state = GameState()
    if values is not None:
        state.values = values
    window.game_state_controller = types.SimpleNamespace(state=state)

    sheet = MagicMock()
    sheet.frames = [MagicMock(width=32, height=32) for _ in range(4)]
    cache = MagicMock()
    cache.get_or_build.return_value = sheet
    factory = MagicMock()
    factory.sheets = cache
    window.animation_factory = factory
    return window


def _start_standard_battle(window: types.SimpleNamespace) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("ko",)),
        opponent_monster=MonsterInstance(OPPONENT, level=5, current_hp=5, known_moves=("tackle",)),
        moves={"tackle": TACKLE, "ko": KO},
        type_chart={},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def test_victory_clip_on_opponent_faint_step() -> None:
    mode = _start_standard_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    faint_step = next(step for step in steps if "is down" in step.line.lower())
    assert faint_step.player_clip == "victory"
    assert faint_step.opponent_clip == "faint"


def test_companion_reinforcement_steps_request_cheer_and_cower() -> None:
    praise_steps = _build_companion_reinforcement_steps("praise", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    assert praise_steps[0].player_clip == "cheer"

    scold_steps = _build_companion_reinforcement_steps("scold", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    assert scold_steps[0].player_clip == "cower"


def test_companion_flee_presentation_requests_flee_clip(monkeypatch: pytest.MonkeyPatch) -> None:
    def _force_flee(
        mind: CompanionMind,
        ctx: DecisionContext,
        rng: object,
        *,
        registry: object = (),
    ) -> tuple[CompanionMind, DecisionResult]:
        updated = replace(mind, last_behavior=FLEE)
        return updated, DecisionResult(behavior_id=FLEE, scores={FLEE: 999.0})

    monkeypatch.setattr("engine.monster.battle_mode.decide", _force_flee)

    window = _window()
    mode = MonsterBattleMode(as_any(window))
    neglected = CompanionMind(
        temperament=Temperament(aggression=10.0, fear=80.0),
        learned=LearnedWeights(),
        trust=5.0,
        bond=0.0,
    )
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=8, current_hp=4, known_moves=("tackle",)),
        opponent_monster=MonsterInstance(OPPONENT, level=6, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart={},
        companion_mode=True,
        companion_mind=neglected,
        rng=random.Random(0),
    )
    assert mode.overlay is not None
    assert mode.overlay.presentation_queue
    flee_step = mode.overlay.presentation_queue[0]
    assert flee_step.player_clip == "flee"


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


def test_capture_attempt_requests_capture_clip_on_opponent() -> None:
    from engine.monster.collection import POCKET_BALL_COUNT_KEY, ensure_monster_collection

    values: dict[str, Any] = {}
    ensure_monster_collection(values)
    values[POCKET_BALL_COUNT_KEY] = 5
    window = _window(values=values)
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=10, known_moves=("tackle",)),
        opponent_monster=MonsterInstance(HARD_CATCH, level=6, current_hp=30, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart={},
        rng=_Rng(0.99),
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    mode.attempt_capture(item_id="pocket_ball")
    assert mode.overlay is not None
    capture_steps = [step for step in mode.overlay.presentation_queue if step.opponent_clip == "capture"]
    assert capture_steps, "expected capture clip on opponent during ball attempt presentation"


def test_asleep_skip_requests_status_clip() -> None:
    window = _window()
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("tackle",)),
        opponent_monster=MonsterInstance(
            FAST_OPPONENT,
            level=5,
            current_hp=30,
            known_moves=("tackle",),
            status_condition="sleep",
            status_turns=3,
        ),
        moves={"tackle": TACKLE},
        type_chart={},
        rng=random.Random(0),
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "tackle")
    steps = mode._build_presentation_steps(before_len, 30, 30)
    status_steps = [step for step in steps if step.opponent_clip == "status"]
    assert status_steps, f"expected status clip step, got {[step.line for step in steps]}"


def test_missing_clip_falls_back_to_idle_with_single_debug_log() -> None:
    textures = tuple(MagicMock(width=32, height=32) for _ in range(2))
    animator = BattleSpriteAnimator(
        textures=textures,
        clips={"idle": BattleSpriteClip(frames=(0,), fps=6.0, loop=True)},
    )
    assert animator.play_clip("cheer") == "idle"
    assert animator._logged_missing_clip_fallback is True
    assert animator.play_clip("victory") == "idle"
    assert animator.play_clip("capture") == "idle"


def test_overlay_applies_companion_clip_triggers() -> None:
    window = _window()
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(
            Species(
                id="sproutling",
                base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
                types=("grass",),
                learnset=("tackle",),
                battle_sprite=BattleSprite(
                    sheet="assets/sprites/sproutling.png",
                    columns=2,
                    rows=1,
                    frame_width=32,
                    frame_height=32,
                    clips={"idle": BattleSpriteClip(frames=(0, 1), fps=6.0, loop=True)},
                ),
            ),
            level=8,
            known_moves=("tackle",),
        ),
        opponent_monster=MonsterInstance(OPPONENT, level=6, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart={},
    )
    overlay = mode.overlay
    assert overlay is not None
    overlay.begin_turn_presentation(
        [BattlePresentationStep("You praise Sproutling.", 30, 20, player_clip="cheer")],
        result=None,
    )
    overlay._advance_presentation()
    assert overlay._player_sprite.last_requested_clip == "cheer"
    assert overlay._player_sprite.last_effective_clip == "idle"
    assert overlay._player_sprite._animator is not None
    assert overlay._player_sprite._animator._logged_missing_clip_fallback is True
