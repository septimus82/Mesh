"""Semantic battle sound-cue vocabulary and presentation assignment contracts."""

from __future__ import annotations

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
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.battle_sound_cues import (
    BATTLE_ACTION,
    BATTLE_CAPTURE_FAIL,
    BATTLE_CAPTURE_SUCCESS,
    BATTLE_COMPANION_PRAISE,
    BATTLE_COMPANION_SCOLD,
    BATTLE_COMPANION_WAIT,
    BATTLE_DEFEAT,
    BATTLE_HIT,
    BATTLE_RESISTED,
    BATTLE_START,
    BATTLE_SUPER_EFFECTIVE,
    BATTLE_SWITCH,
    BATTLE_VICTORY,
    KNOWN_BATTLE_SOUND_CUES,
)
from engine.monster.battle_terms import DEFAULT_BATTLE_TERMS
from engine.monster.companion_mind import CompanionMind, DecisionContext, DecisionResult
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)
EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)

PLAYER = Species(
    id="player_mon",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("tackle", "ko", "ember"),
)
OPPONENT = Species(
    id="opponent_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("normal",),
    learnset=("tackle",),
)
GRASS_OPPONENT = Species(
    id="grass_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("grass",),
    learnset=("tackle",),
)
FIRE_OPPONENT = Species(
    id="fire_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("fire",),
    learnset=("tackle",),
)
HARD_CATCH = Species(
    id="hard_catch",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
    capture_rate=10,
)

TYPE_CHART = {
    "fire": {"grass": 2.0, "fire": 0.5, "water": 0.5},
    "water": {"fire": 2.0, "grass": 0.5},
    "normal": {"normal": 1.0},
}


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


def _start_battle(
    window: types.SimpleNamespace,
    *,
    player: Species = PLAYER,
    opponent: Species = OPPONENT,
    player_hp: int = 30,
    opponent_hp: int = 5,
    moves: dict[str, Move] | None = None,
    type_chart: dict[str, dict[str, float]] | None = None,
    player_moves: tuple[str, ...] = ("ko",),
) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    mode.start_battle(
        player_monster=MonsterInstance(player, level=10, current_hp=player_hp, known_moves=player_moves),
        opponent_monster=MonsterInstance(opponent, level=5, current_hp=opponent_hp, known_moves=("tackle",)),
        moves=moves or {"tackle": TACKLE, "ko": KO, "ember": EMBER},
        type_chart=type_chart or {},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _cues(steps: list[BattlePresentationStep]) -> list[str]:
    return [cue for step in steps if (cue := step.audio_cue) is not None]


def test_known_battle_sound_cues_are_stable_and_unique() -> None:
    cues = sorted(KNOWN_BATTLE_SOUND_CUES)
    assert len(cues) == len(set(cues))
    assert BATTLE_START in cues
    assert all(cue.startswith("battle.") for cue in cues)
    assert not any("/" in cue or ".wav" in cue for cue in cues)


def test_presentation_steps_default_to_no_audio_cue() -> None:
    step = BattlePresentationStep("line", 10, 10)
    assert step.audio_cue is None


def test_intro_sets_battle_start_cue_on_overlay() -> None:
    mode = _start_battle(_window())
    assert mode.overlay is not None
    assert mode.overlay.intro_audio_cue == BATTLE_START


def test_normal_damaging_attack_cue_sequence() -> None:
    mode = _start_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    assert _cues(steps) == [BATTLE_HIT, BATTLE_VICTORY]


def test_super_effective_move_uses_super_effective_cue() -> None:
    mode = _start_battle(
        _window(),
        opponent=GRASS_OPPONENT,
        opponent_hp=30,
        player_moves=("ember",),
        type_chart=TYPE_CHART,
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ember")
    steps = mode._build_presentation_steps(before_len, 30, 30)
    assert _cues(steps)[0] == BATTLE_SUPER_EFFECTIVE


def test_resisted_move_uses_resisted_cue() -> None:
    mode = _start_battle(
        _window(),
        opponent=FIRE_OPPONENT,
        opponent_hp=30,
        player_moves=("ember",),
        type_chart=TYPE_CHART,
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ember")
    steps = mode._build_presentation_steps(before_len, 30, 30)
    assert _cues(steps)[0] == BATTLE_RESISTED


def test_faint_cue_occurs_once_per_ko() -> None:
    mode = _start_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    assert _cues(steps) == [BATTLE_HIT, BATTLE_VICTORY]


def test_victory_cue_once_and_after_hit() -> None:
    mode = _start_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    cues = _cues(steps)
    assert cues.count(BATTLE_VICTORY) == 1
    assert cues.index(BATTLE_HIT) < cues.index(BATTLE_VICTORY)


def test_switch_presentation_uses_switch_cue() -> None:
    mode = _start_battle(
        _window(),
        player_hp=30,
        opponent_hp=30,
        player_moves=("tackle",),
    )
    mode.controller.player_party.append(
        MonsterInstance(PLAYER, level=5, current_hp=20, known_moves=("tackle",)),
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_switch(1)
    steps = mode._build_presentation_steps(before_len, 30, 30)
    assert BATTLE_SWITCH in _cues(steps)


def test_capture_success_and_failure_cues_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.monster.capture import CaptureResult

    window = _window()
    values = window.game_state_controller.state.values
    from engine.monster.collection import POCKET_BALL_COUNT_KEY, ensure_monster_collection

    ensure_monster_collection(values)
    values[POCKET_BALL_COUNT_KEY] = 5

    monkeypatch.setattr(
        "engine.monster.battle_mode.resolve_capture",
        lambda _monster, **kwargs: CaptureResult(
            caught=True, roll=0.0, chance=1.0, capture_rate=190, hp_fraction=0.1, ball_bonus=1.0
        ),
    )
    success_mode = _start_battle(window, opponent=HARD_CATCH, opponent_hp=1)
    success_mode.attempt_capture()
    success_steps = success_mode.overlay.presentation_queue  # type: ignore[union-attr]
    assert _cues(success_steps) == [BATTLE_CAPTURE_SUCCESS]

    monkeypatch.setattr(
        "engine.monster.battle_mode.resolve_capture",
        lambda _monster, **kwargs: CaptureResult(
            caught=False, roll=1.0, chance=0.1, capture_rate=10, hp_fraction=1.0, ball_bonus=1.0
        ),
    )

    def _no_counter(_controller: object) -> MoveAction:
        raise RuntimeError("no counter")

    fail_window = _window(values=dict(values))
    fail_mode = _start_battle(fail_window, opponent=HARD_CATCH, opponent_hp=30)
    fail_mode.controller.opponent_action_provider = _no_counter  # type: ignore[method-assign]
    fail_mode.attempt_capture()
    fail_steps = fail_mode.overlay.presentation_queue  # type: ignore[union-attr]
    assert _cues(fail_steps) == [BATTLE_CAPTURE_FAIL]


def test_failed_capture_with_counter_attack_starts_with_throw_cue(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.monster.capture import CaptureResult

    window = _window()
    values = window.game_state_controller.state.values
    from engine.monster.collection import POCKET_BALL_COUNT_KEY, ensure_monster_collection

    ensure_monster_collection(values)
    values[POCKET_BALL_COUNT_KEY] = 5
    monkeypatch.setattr(
        "engine.monster.battle_mode.resolve_capture",
        lambda _monster, **kwargs: CaptureResult(
            caught=False, roll=1.0, chance=0.1, capture_rate=10, hp_fraction=1.0, ball_bonus=1.0
        ),
    )
    mode = _start_battle(window, opponent=HARD_CATCH, opponent_hp=30, player_hp=30)
    mode.attempt_capture()
    assert mode.overlay is not None
    assert mode.overlay.presentation_queue[0].audio_cue == "battle.capture_throw"


def test_companion_reinforcement_cues() -> None:
    praise = _build_companion_reinforcement_steps("praise", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    scold = _build_companion_reinforcement_steps("scold", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    wait = _build_companion_reinforcement_steps("wait", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    assert praise[0].audio_cue == BATTLE_COMPANION_PRAISE
    assert scold[0].audio_cue == BATTLE_COMPANION_SCOLD
    assert wait[0].audio_cue == BATTLE_COMPANION_WAIT


def test_defeat_cue_on_party_wipe() -> None:
    mode = _start_battle(_window(), player_hp=1, opponent_hp=30, player_moves=("tackle",))
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "tackle")
    steps = mode._build_presentation_steps(before_len, 1, 30)
    result = mode.controller.result
    mode._append_defeat_step_if_lost(steps, result, player_hp=0, opponent_hp=30)
    assert steps[-1].audio_cue == BATTLE_DEFEAT


def test_cue_assignment_does_not_depend_on_narration_text() -> None:
    custom_terms = replace(
        DEFAULT_BATTLE_TERMS,
        move_hit="CUSTOM HIT LINE {actor} {move} {target} {damage}",
        move_miss="CUSTOM MISS {actor} {move}",
        ko_foe="CUSTOM KO {name}",
    )
    mode = _start_battle(_window())
    mode.terms = custom_terms
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    assert all("CUSTOM" in step.line for step in steps[:2])
    assert _cues(steps) == [BATTLE_HIT, BATTLE_VICTORY]


def test_presentation_cue_order_matches_visible_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[str | None] = []
    mode = _start_battle(_window())
    overlay = mode.overlay
    assert overlay is not None

    original_advance = overlay._advance_presentation

    def record_advance() -> None:
        if overlay.presentation_queue:
            emitted.append(overlay.presentation_queue[0].audio_cue)
        original_advance()

    monkeypatch.setattr(overlay, "_advance_presentation", record_advance)
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    overlay.begin_turn_presentation(steps, result=mode.controller.result)
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()
    assert emitted == [BATTLE_HIT, BATTLE_VICTORY]


def test_companion_autonomous_attack_prepends_action_cue(monkeypatch: pytest.MonkeyPatch) -> None:
    def _force_attack(
        mind: CompanionMind,
        ctx: DecisionContext,
        rng: object,
        *,
        registry: object = (),
    ) -> tuple[CompanionMind, DecisionResult]:
        from engine.monster.companion_mind import ATTACK

        return mind, DecisionResult(behavior_id=ATTACK, scores={ATTACK: 1.0})

    monkeypatch.setattr("engine.monster.battle_mode.decide", _force_attack)
    mode = MonsterBattleMode(as_any(_window()))
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("tackle",)),
        opponent_monster=MonsterInstance(OPPONENT, level=5, current_hp=5, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart={},
        companion_mode=True,
        companion_mind=CompanionMind(),
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    assert mode.overlay is not None
    cues = _cues(mode.overlay.presentation_queue)
    assert cues[0] == BATTLE_ACTION
    assert BATTLE_HIT in cues
