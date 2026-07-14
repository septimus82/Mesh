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
    KNOWN_BATTLE_SOUND_CUES,
)
from engine.monster.battle_terms import DEFAULT_BATTLE_TERMS
from engine.monster.companion_mind import ATTACK, CompanionMind, DecisionContext, DecisionResult
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)
EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)
MISS = Move(id="whiff", type="normal", power=0, accuracy=0, pp=5)

PLAYER = Species(
    id="player_mon",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("tackle", "ko", "ember", "whiff"),
)
OPPONENT = Species(
    id="opponent_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("normal",),
    learnset=("tackle",),
)
GRASS_LEAD = Species(
    id="grass_lead",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("grass",),
    learnset=("tackle",),
)
FIRE_BENCH = Species(
    id="fire_bench",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("fire",),
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
TRAINER_BENCH = Species(
    id="trainer_bench",
    base_stats=BattleStats(hp=28, atk=18, defense=10, spd=6),
    types=("normal",),
    learnset=("tackle",),
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
    opponent_party: list[MonsterInstance] | None = None,
) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    opponent_monster = MonsterInstance(opponent, level=5, current_hp=opponent_hp, known_moves=("tackle",))
    mode.start_battle(
        player_monster=MonsterInstance(player, level=10, current_hp=player_hp, known_moves=player_moves),
        opponent_monster=opponent_monster,
        opponent_party=opponent_party,
        moves=moves or {"tackle": TACKLE, "ko": KO, "ember": EMBER, "whiff": MISS},
        type_chart=type_chart or {},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _flat_cues(steps: list[BattlePresentationStep]) -> list[str]:
    cues: list[str] = []
    for step in steps:
        cues.extend(step.audio_cues)
    return cues


def test_exact_vocabulary_equals_fifteen_approved_semantic_ids() -> None:
    assert len(APPROVED_BATTLE_SOUND_CUES) == 15
    assert len(set(APPROVED_BATTLE_SOUND_CUES)) == 15
    assert set(APPROVED_BATTLE_SOUND_CUES) == KNOWN_BATTLE_SOUND_CUES
    for cue in APPROVED_BATTLE_SOUND_CUES:
        assert cue.startswith("battle.")
        assert "/" not in cue
        assert ".wav" not in cue


def test_presentation_steps_default_to_empty_cue_sequence() -> None:
    step = BattlePresentationStep("line", 10, 10)
    assert step.audio_cues == ()


def test_intro_sets_battle_start_cue_on_overlay() -> None:
    mode = _start_battle(_window())
    assert mode.overlay is not None
    assert mode.overlay.intro_audio_cue == BATTLE_START


def test_normal_hit_sequence_is_action_then_hit() -> None:
    mode = _start_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    move_step = steps[0]
    assert move_step.audio_cues == (BATTLE_ACTION, BATTLE_HIT)


def test_super_effective_sequence_includes_effectiveness_after_hit() -> None:
    mode = _start_battle(
        _window(),
        opponent=GRASS_LEAD,
        opponent_hp=30,
        player_moves=("ember",),
        type_chart=TYPE_CHART,
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ember")
    steps = mode._build_presentation_steps(before_len, 30, 30)
    assert steps[0].audio_cues == (BATTLE_ACTION, BATTLE_HIT, BATTLE_SUPER_EFFECTIVE)


def test_resisted_sequence_includes_effectiveness_after_hit() -> None:
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
    assert steps[0].audio_cues == (BATTLE_ACTION, BATTLE_HIT, BATTLE_RESISTED)


def test_miss_sequence_is_action_only() -> None:
    mode = _start_battle(_window(), player_moves=("whiff",))
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "whiff")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    assert steps[0].audio_cues == (BATTLE_ACTION,)


def test_final_knockout_sequence_includes_faint_and_victory() -> None:
    mode = _start_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    steps.extend(mode._apply_victory_progression_steps(30, 5))
    assert _flat_cues(steps) == [
        BATTLE_ACTION,
        BATTLE_HIT,
        BATTLE_FAINT,
        BATTLE_VICTORY,
    ]


def test_faint_emits_one_faint_cue_per_knockout() -> None:
    mode = _start_battle(_window())
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    assert _flat_cues(steps).count(BATTLE_FAINT) == 1


def test_player_wipe_sequence_includes_faint_and_defeat() -> None:
    mode = _start_battle(_window(), player_hp=1, opponent_hp=30)
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_player_pass_turn(guarding=False)
    steps = mode._build_presentation_steps(before_len, 1, 30)
    mode._append_defeat_step_if_lost(steps, mode.controller.result, player_hp=0, opponent_hp=30)
    assert _flat_cues(steps) == [BATTLE_ACTION, BATTLE_HIT, BATTLE_FAINT, BATTLE_DEFEAT]


def test_non_final_knockout_faint_then_switch_without_victory() -> None:
    lead = MonsterInstance(GRASS_LEAD, level=5, current_hp=5, known_moves=("tackle",))
    bench = MonsterInstance(TRAINER_BENCH, level=8, current_hp=20, known_moves=("tackle",))
    mode = _start_battle(
        _window(),
        opponent=GRASS_LEAD,
        opponent_hp=5,
        opponent_party=[lead, bench],
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    cues = _flat_cues(steps)
    assert cues.count(BATTLE_FAINT) == 1
    assert BATTLE_SWITCH in cues
    assert BATTLE_VICTORY not in cues


def test_effectiveness_uses_logged_multiplier_after_opponent_auto_switch() -> None:
    lead = MonsterInstance(GRASS_LEAD, level=5, current_hp=5, known_moves=("tackle",))
    bench = MonsterInstance(FIRE_BENCH, level=8, current_hp=30, known_moves=("tackle",))
    mode = _start_battle(
        _window(),
        opponent=GRASS_LEAD,
        opponent_hp=5,
        player_moves=("ember",),
        type_chart=TYPE_CHART,
        opponent_party=[lead, bench],
    )
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ember")
    assert mode.controller.opponent.species.id == "fire_bench"
    move_entry = mode.controller.turn_log[before_len]
    assert move_entry.type_multiplier == 2.0
    steps = mode._build_presentation_steps(before_len, 30, 5)
    assert steps[0].audio_cues == (BATTLE_ACTION, BATTLE_HIT, BATTLE_SUPER_EFFECTIVE)


def test_capture_success_sequence_is_throw_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
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
    mode = _start_battle(window, opponent=HARD_CATCH, opponent_hp=1)
    mode.attempt_capture()
    assert mode.overlay is not None
    assert mode.overlay.presentation_queue[0].audio_cues == (BATTLE_CAPTURE_THROW, BATTLE_CAPTURE_SUCCESS)


def test_capture_failure_without_counter_is_throw_then_fail(monkeypatch: pytest.MonkeyPatch) -> None:
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

    def _no_counter(_controller: object) -> MoveAction:
        raise RuntimeError("no counter")

    mode = _start_battle(window, opponent=HARD_CATCH, opponent_hp=30)
    mode.controller.opponent_action_provider = _no_counter  # type: ignore[method-assign]
    mode.attempt_capture()
    assert mode.overlay is not None
    assert mode.overlay.presentation_queue[0].audio_cues == (BATTLE_CAPTURE_THROW, BATTLE_CAPTURE_FAIL)


def test_capture_failure_with_counter_includes_throw_fail_then_action(monkeypatch: pytest.MonkeyPatch) -> None:
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
    cues = _flat_cues(mode.overlay.presentation_queue)
    assert cues[:3] == [BATTLE_CAPTURE_THROW, BATTLE_CAPTURE_FAIL, BATTLE_ACTION]


def test_blocked_capture_emits_no_throw_cue() -> None:
    window = _window()
    values = window.game_state_controller.state.values
    from engine.monster.collection import POCKET_BALL_COUNT_KEY, ensure_monster_collection

    ensure_monster_collection(values)
    values[POCKET_BALL_COUNT_KEY] = 0
    mode = _start_battle(window, opponent=HARD_CATCH, opponent_hp=30)
    mode.attempt_capture()
    assert mode.overlay is not None
    assert mode.overlay.presentation_queue == []


def test_companion_reinforcement_cues() -> None:
    praise = _build_companion_reinforcement_steps("praise", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    scold = _build_companion_reinforcement_steps("scold", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    wait = _build_companion_reinforcement_steps("wait", "Sproutling", 20, 15, DEFAULT_BATTLE_TERMS)
    assert praise[0].audio_cues == (BATTLE_COMPANION_PRAISE,)
    assert scold[0].audio_cues == (BATTLE_COMPANION_SCOLD,)
    assert wait[0].audio_cues == (BATTLE_COMPANION_WAIT,)


def test_companion_attack_does_not_duplicate_action_cue(monkeypatch: pytest.MonkeyPatch) -> None:
    def _force_attack(
        mind: CompanionMind,
        ctx: DecisionContext,
        rng: object,
        *,
        registry: object = (),
    ) -> tuple[CompanionMind, DecisionResult]:
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
    cues = _flat_cues(mode.overlay.presentation_queue)
    assert cues.count(BATTLE_ACTION) == 1
    assert cues[0] == BATTLE_ACTION


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
    assert _flat_cues(steps) == [BATTLE_ACTION, BATTLE_HIT, BATTLE_FAINT]


def test_presentation_cue_order_matches_visible_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[tuple[str, ...]] = []
    mode = _start_battle(_window())
    overlay = mode.overlay
    assert overlay is not None

    original_advance = overlay._advance_presentation

    def record_advance() -> None:
        if overlay.presentation_queue:
            emitted.append(overlay.presentation_queue[0].audio_cues)
        original_advance()

    monkeypatch.setattr(overlay, "_advance_presentation", record_advance)
    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    overlay.begin_turn_presentation(steps, result=mode.controller.result)
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()
    assert emitted == [(BATTLE_ACTION, BATTLE_HIT), (BATTLE_FAINT,)]
