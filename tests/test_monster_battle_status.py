from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.game_state_controller import GameState
from engine.input_controller import InputController
from engine.monster.battle_controller import MonsterBattleController, MoveAction
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, MoveStatusInflict, Species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

TYPE_CHART = {"normal": {}}

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
POISON_STING = Move(
    id="poison_sting",
    type="normal",
    power=1,
    accuracy=100,
    pp=20,
    status_inflict=MoveStatusInflict("poison", 1.0),
)
SLEEP_POWDER = Move(
    id="sleep_powder",
    type="normal",
    power=0,
    accuracy=100,
    pp=15,
    status_inflict=MoveStatusInflict("sleep", 1.0),
)
NO_STATUS = Move(
    id="no_status",
    type="normal",
    power=0,
    accuracy=100,
    pp=15,
    status_inflict=MoveStatusInflict("sleep", 0.0),
)

PLAYER = Species(id="player", base_stats=BattleStats(hp=40, atk=10, defense=10, spd=20), types=("normal",), learnset=("tackle",))
SLOW_PLAYER = Species(id="slow_player", base_stats=BattleStats(hp=40, atk=10, defense=10, spd=1), types=("normal",), learnset=("tackle",))
OPPONENT = Species(id="opponent", base_stats=BattleStats(hp=40, atk=10, defense=10, spd=30), types=("normal",), learnset=("sleep_powder",))


class _Console:
    active = False

    def process_key(self, _key: int, _modifiers: int) -> bool:
        return False


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


def _controller(*, rng: _Rng | None = None, opponent_move: str = "tackle", player: MonsterInstance | None = None) -> MonsterBattleController:
    return MonsterBattleController(
        player=player or MonsterInstance(PLAYER, level=10, known_moves=("tackle", "poison_sting")),
        opponent=MonsterInstance(OPPONENT, level=10, known_moves=("sleep_powder", "tackle")),
        moves={move.id: move for move in (TACKLE, POISON_STING, SLEEP_POWDER, NO_STATUS)},
        type_chart=TYPE_CHART,
        rng=rng,
        opponent_action_provider=lambda _controller: MoveAction("opponent", opponent_move),
    )


def _window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.game_over = False
    window.show_debug = False
    window.command_palette_enabled = False
    window.command_palette_prompt_active = False
    window.scene_persist_armed = False
    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)
    window.engine_config = types.SimpleNamespace(input_bindings={"move_up": ["W"], "interact": ["E"]})
    window.ui_controller = UIController(as_any(window))
    window.input_controller = InputController(as_any(window))
    window.monster_battle_mode_active = False
    window._mesh_event_queue = []
    window.emit_event = lambda event: window._mesh_event_queue.append(event)
    window.game_state_controller = types.SimpleNamespace(state=GameState())
    window.console_log = MagicMock()
    return window


def _press(window: types.SimpleNamespace, key: int, modifiers: int = 0) -> bool:
    return bool(window.input_controller.on_key_press(key, modifiers))


def test_status_inflict_applies_under_fixed_seed() -> None:
    controller = _controller(rng=_Rng(0.0, 0.0, 0.0))

    controller.submit_action("player", "poison_sting")

    status_events = [entry.status_event for entry in controller.turn_log if entry.kind == "status"]
    assert "poisoned" in status_events
    assert controller.opponent.status_condition == "poison"


def test_status_inflict_does_not_apply_when_roll_fails() -> None:
    controller = _controller(rng=_Rng(0.0), opponent_move="no_status")
    controller.opponent = MonsterInstance(OPPONENT, level=10, known_moves=("no_status",))

    controller.submit_action("player", "tackle")

    assert not any(entry.kind == "status" for entry in controller.turn_log)
    assert controller.opponent.status_condition is None


def test_poison_end_of_turn_can_end_battle_as_won() -> None:
    controller = _controller(
        rng=_Rng(0.0, 0.0, 0.0),
        player=MonsterInstance(PLAYER, level=10, known_moves=("poison_sting",)),
    )
    controller.opponent = MonsterInstance(OPPONENT, level=10, current_hp=3, known_moves=("tackle",))

    result = controller.submit_action("player", "poison_sting")

    assert result is not None
    assert result.outcome == "won"
    assert controller.opponent.fainted is True
    assert any(entry.status_event == "poison_damage" for entry in controller.turn_log if entry.kind == "status")


def test_sleep_skips_player_actions_then_wakes() -> None:
    controller = _controller(rng=_Rng(0.99, 0.99, 0.99, 0.99, 0.99, 0.99), opponent_move="sleep_powder")
    controller.player = MonsterInstance(SLOW_PLAYER, level=10, known_moves=("tackle",))
    controller.opponent = MonsterInstance(OPPONENT, level=10, known_moves=("sleep_powder", "tackle"))

    controller.submit_action("player", "tackle")
    assert controller.player.status_condition == "sleep"

    while controller.result is None and controller.player.status_condition == "sleep":
        controller.submit_action("player", "tackle")

    asleep_skips = [entry for entry in controller.turn_log if entry.kind == "status" and entry.status_event == "asleep_skip"]
    woke_ups = [entry for entry in controller.turn_log if entry.kind == "status" and entry.status_event == "woke_up"]

    assert len(asleep_skips) >= 3
    assert woke_ups
    assert controller.player.status_condition is None


def test_status_lines_are_presented_in_order() -> None:
    window = _window()
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER, level=10, known_moves=("poison_sting",)),
        opponent_monster=MonsterInstance(OPPONENT, level=10, current_hp=40, known_moves=("tackle",)),
        moves={move.id: move for move in (TACKLE, POISON_STING, SLEEP_POWDER, NO_STATUS)},
        type_chart=TYPE_CHART,
        rng=_Rng(0.0, 0.0, 0.0, 0.0),
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    overlay = mode.overlay
    assert overlay is not None

    _press(window, optional_arcade.arcade.key.ENTER)
    _press(window, optional_arcade.arcade.key.ENTER)

    assert overlay.menu_state == "presenting"
    lines = [step.line for step in overlay.presentation_queue]
    poisoned_index = next(index for index, line in enumerate(lines) if "was poisoned!" in line)
    hurt_index = next(index for index, line in enumerate(lines) if "is hurt by poison!" in line)
    assert poisoned_index < hurt_index
