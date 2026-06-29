from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.input_controller import InputController
from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT, MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast


TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)

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
    window.console_log = MagicMock()
    return window


def _start_ui_battle(window: types.SimpleNamespace, *, player_hp: int | None = None) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER_SPECIES, level=10, current_hp=player_hp, known_moves=("ember", "tackle")),
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, known_moves=("tackle",)),
        moves={move.id: move for move in (TACKLE, EMBER, KO)},
        type_chart={"fire": {"water": 0.5}, "grass": {"water": 2.0}},
        return_context={"scene_path": "scenes/field.json"},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _press(window: types.SimpleNamespace, key: int, modifiers: int = 0) -> bool:
    return bool(window.input_controller.on_key_press(key, modifiers))


def test_keyboard_fight_then_move_submits_move_and_advances_turn() -> None:
    window = _window()
    mode = _start_ui_battle(window)
    overlay = mode.overlay
    assert overlay is not None

    assert _press(window, optional_arcade.arcade.key.ENTER) is True
    assert overlay.menu_state == "fight"
    assert _press(window, optional_arcade.arcade.key.ENTER) is True

    assert mode.controller is not None
    assert mode.controller.turn_number == 2
    assert mode.controller.turn_log[0].side == "player"
    assert mode.controller.turn_log[0].move_id == "ember"


def test_mouse_bag_ball_routes_capture_attempt_action() -> None:
    window = _window()
    mode = _start_ui_battle(window)
    overlay = mode.overlay
    assert overlay is not None

    overlay.button_rects = {"menu:bag": (10.0, 10.0, 80.0, 30.0)}
    assert window.input_controller.on_mouse_press(20.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert overlay.menu_state == "bag"
    overlay.button_rects = {"capture:pocket_ball": (10.0, 10.0, 120.0, 30.0)}
    assert window.input_controller.on_mouse_press(20.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert mode.active is False
    assert window.paused is False
    assert any(event.type == MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT for event in window._mesh_event_queue)


def test_keyboard_run_routes_flee_and_ends_battle_mode() -> None:
    window = _window()
    mode = _start_ui_battle(window)

    assert _press(window, optional_arcade.arcade.key.DOWN) is True
    assert _press(window, optional_arcade.arcade.key.DOWN) is True
    assert _press(window, optional_arcade.arcade.key.ENTER) is True

    assert mode.active is False
    assert window.paused is False
    assert window.ui_controller.input_blocked is False


def test_overlay_blocks_overworld_input_while_active(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window()
    _start_ui_battle(window)
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr("engine.input_controller.dispatch_action", dispatch)

    window.input_controller.on_key_press(optional_arcade.arcade.key.W, 0)
    window.input_controller.update(0.016)

    assert window.ui_controller.input_blocked is True
    dispatch.assert_not_called()


def test_hp_and_log_snapshot_update_after_resolved_turn() -> None:
    window = _window()
    mode = _start_ui_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    before = overlay.snapshot()

    _press(window, optional_arcade.arcade.key.ENTER)
    _press(window, optional_arcade.arcade.key.ENTER)
    after = overlay.snapshot()

    assert after["opponent_hp"] < before["opponent_hp"]
    assert "Sproutling used ember" in str(after["log_line"])


def test_debug_ctrl_b_launches_fixture_battle_through_key_router() -> None:
    window = _window()
    window.show_debug = True
    window.start_debug_monster_battle = MagicMock(return_value=True)

    handled = window.input_controller.on_key_press(
        optional_arcade.arcade.key.B,
        optional_arcade.arcade.key.MOD_CTRL,
    )

    assert handled is True
    window.start_debug_monster_battle.assert_called_once_with()
