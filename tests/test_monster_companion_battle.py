from __future__ import annotations

import random
import types
from collections import Counter
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import load_config
from engine.game_runtime import input_dispatch
from engine.game_state_controller import GameState
from engine.input_controller import InputController
from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.companion_mind import (
    ATTACK,
    PRAISE_LEARN_DELTA,
    CompanionMind,
    DecisionContext,
    LearnedWeights,
    Temperament,
    decide,
    praise,
)
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast


TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)

PLAYER_SPECIES = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=12, defense=10, spd=20),
    types=("grass",),
    learnset=("ember", "tackle"),
)
OPPONENT_SPECIES = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)


class _Console:
    active = False

    def process_key(self, _key: int, _modifiers: int) -> bool:
        return False


def _window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.game_over = False
    window.show_debug = False
    window.monster_battle_mode_active = False
    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)
    window.ui_controller = UIController(as_any(window))
    window.input_controller = InputController(as_any(window))
    window.game_state_controller = types.SimpleNamespace(state=GameState())
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    return window


def _start_companion_battle(
    window: types.SimpleNamespace,
    *,
    mind: CompanionMind | None = None,
    rng: random.Random | None = None,
) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER_SPECIES, level=10, known_moves=("ember", "tackle")),
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, current_hp=40, known_moves=("tackle",)),
        moves={TACKLE.id: TACKLE, EMBER.id: EMBER},
        type_chart={"fire": {"water": 0.5}, "grass": {"water": 2.0}},
        companion_mode=True,
        companion_mind=mind
        or CompanionMind(temperament=Temperament(aggression=55.0, fear=10.0), learned=LearnedWeights(), trust=50.0),
        rng=rng or random.Random(0),
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _start_command_battle(window: types.SimpleNamespace) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER_SPECIES, level=10, known_moves=("ember", "tackle")),
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, current_hp=40, known_moves=("tackle",)),
        moves={TACKLE.id: TACKLE, EMBER.id: EMBER},
        type_chart={"fire": {"water": 0.5}, "grass": {"water": 2.0}},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _drain_presentation(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()


def test_companion_root_menu_shows_praise_scold_wait() -> None:
    window = _window()
    mode = _start_companion_battle(window)
    overlay = mode.overlay
    assert overlay is not None

    _drain_presentation(mode)

    actions = overlay._current_actions()
    labels = [label for _, label in actions]
    assert labels == ["Praise", "Scold", "Wait", "Ball"]
    assert not any("Fight" in label for label in labels)


def test_command_battler_root_menu_still_shows_fight_bag_run() -> None:
    window = _window()
    mode = _start_command_battle(window)
    overlay = mode.overlay
    assert overlay is not None

    labels = [label for _, label in overlay._current_actions()]
    assert "Fight" in labels
    assert "Bag" in labels
    assert "Run" in labels
    assert "Praise" not in labels


def test_companion_monster_action_comes_from_mind_not_player_move_input() -> None:
    window = _window()
    mode = _start_companion_battle(window, rng=random.Random(42))
    overlay = mode.overlay
    assert overlay is not None
    assert mode.companion_mind is not None

    _drain_presentation(mode)
    assert mode.companion_awaiting_reinforcement is True
    assert mode._last_companion_behavior in {ATTACK, "DEFEND", "HESITATE"}
    assert mode.companion_mind.last_behavior == mode._last_companion_behavior
    if mode._last_companion_behavior == ATTACK:
        assert any(entry.side == "player" and entry.kind == "move" for entry in mode.controller.turn_log)


def test_praise_reinforces_last_behavior_trust_and_learned_weight() -> None:
    window = _window()
    mode = _start_companion_battle(window, rng=random.Random(1))
    _drain_presentation(mode)

    assert mode.companion_mind is not None
    behavior = mode.companion_mind.last_behavior
    assert behavior is not None
    learn_before = float(getattr(mode.companion_mind.learned, behavior))
    trust_before = mode.companion_mind.trust
    mode.submit_companion_reinforcement("praise")
    _drain_presentation(mode)

    assert float(getattr(mode.companion_mind.learned, behavior)) == pytest.approx(learn_before + PRAISE_LEARN_DELTA)
    assert mode.companion_mind.trust > trust_before


def test_scold_reinforces_down_trust_and_up_fear() -> None:
    window = _window()
    mode = _start_companion_battle(window, rng=random.Random(2))
    _drain_presentation(mode)

    assert mode.companion_mind is not None
    behavior = mode.companion_mind.last_behavior
    assert behavior is not None
    learn_before = float(getattr(mode.companion_mind.learned, behavior))
    trust_before = mode.companion_mind.trust
    fear_before = mode.companion_mind.temperament.fear
    mode.submit_companion_reinforcement("scold")
    _drain_presentation(mode)

    assert float(getattr(mode.companion_mind.learned, behavior)) < learn_before
    assert mode.companion_mind.trust < trust_before
    assert mode.companion_mind.temperament.fear > fear_before


def test_repeated_praise_of_attack_shifts_companion_picks_toward_attack() -> None:
    baseline_mind = CompanionMind(
        temperament=Temperament(aggression=20.0, fear=10.0),
        learned=LearnedWeights(),
        trust=50.0,
    )
    ctx = DecisionContext()
    baseline = Counter(
        decide(baseline_mind, ctx, random.Random(seed))[1].behavior_id for seed in range(300)
    )

    trained = baseline_mind
    for _ in range(10):
        trained = praise(replace(trained, last_behavior=ATTACK))

    reinforced = Counter(decide(trained, ctx, random.Random(seed))[1].behavior_id for seed in range(300))
    assert reinforced[ATTACK] / sum(reinforced.values()) > baseline[ATTACK] / sum(baseline.values()) + 0.08


def test_companion_battle_is_deterministic_under_fixed_seed() -> None:
    window_a = _window()
    window_b = _window()
    mode_a = _start_companion_battle(window_a, rng=random.Random(999))
    mode_b = _start_companion_battle(window_b, rng=random.Random(999))

    _drain_presentation(mode_a)
    _drain_presentation(mode_b)

    assert mode_a._last_companion_behavior == mode_b._last_companion_behavior
    assert mode_a.companion_mind.last_behavior == mode_b.companion_mind.last_behavior


def test_f8_launches_companion_battle_when_debug_mode_enabled() -> None:
    window = _window()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = True
    window.start_debug_companion_monster_battle = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F8,
        0,
    )

    window.start_debug_companion_monster_battle.assert_called_once_with()


def test_f8_does_not_launch_companion_battle_when_debug_mode_disabled() -> None:
    window = _window()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = False
    window.start_debug_companion_monster_battle = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F8,
        0,
    )

    window.start_debug_companion_monster_battle.assert_not_called()
