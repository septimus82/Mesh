from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import load_config
from engine.game_runtime import input_dispatch
from engine.game_state_controller import GameState
from engine.input_controller import InputController
from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT, MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.collection import MONSTER_INSTANCES_KEY, MONSTER_PARTY_KEY, POCKET_BALL_COUNT_KEY, serialize_monster_instance
from engine.monster.progression import xp_required_for_level
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


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


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


def _start_ui_battle(
    window: types.SimpleNamespace,
    *,
    player_hp: int | None = None,
    opponent_hp: int | None = None,
    player_moves: tuple[str, ...] = ("ember", "tackle"),
    rng: object | None = None,
    return_context: dict[str, object] | None = None,
) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER_SPECIES, level=10, current_hp=player_hp, known_moves=player_moves),
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, current_hp=opponent_hp, known_moves=("tackle",)),
        moves={move.id: move for move in (TACKLE, EMBER, KO)},
        type_chart={"fire": {"water": 0.5}, "grass": {"water": 2.0}},
        return_context=return_context or {"scene_path": "scenes/field.json"},
        rng=rng,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _press(window: types.SimpleNamespace, key: int, modifiers: int = 0) -> bool:
    return bool(window.input_controller.on_key_press(key, modifiers))


def _submit_first_move(window: types.SimpleNamespace) -> None:
    assert _press(window, optional_arcade.arcade.key.ENTER) is True
    assert _press(window, optional_arcade.arcade.key.ENTER) is True


def test_keyboard_fight_then_move_submits_move_and_advances_turn() -> None:
    window = _window()
    mode = _start_ui_battle(window)
    overlay = mode.overlay
    assert overlay is not None

    _submit_first_move(window)

    assert mode.controller is not None
    assert mode.controller.turn_number == 2
    assert mode.controller.turn_log[0].side == "player"
    assert mode.controller.turn_log[0].move_id == "ember"
    assert overlay.menu_state == "presenting"


def test_mouse_bag_ball_routes_capture_attempt_action() -> None:
    window = _window()
    mode = _start_ui_battle(window, rng=_Rng(0.0))
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
    values = window.game_state_controller.state.values
    assert values[POCKET_BALL_COUNT_KEY] == 2
    assert len(values[MONSTER_PARTY_KEY]) == 1


def test_capture_failure_consumes_ball_and_battle_continues() -> None:
    window = _window()
    mode = _start_ui_battle(window, rng=_Rng(0.99, 0.0))
    overlay = mode.overlay
    assert overlay is not None
    values = window.game_state_controller.state.values

    overlay.button_rects = {"menu:bag": (10.0, 10.0, 80.0, 30.0)}
    assert window.input_controller.on_mouse_press(20.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    overlay.button_rects = {"capture:pocket_ball": (10.0, 10.0, 120.0, 30.0)}
    assert window.input_controller.on_mouse_press(20.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert mode.active is True
    assert values[POCKET_BALL_COUNT_KEY] == 2
    assert overlay.menu_state == "presenting"
    assert "broke free" in overlay.presentation_queue[0].line


def test_capture_with_zero_balls_is_blocked() -> None:
    window = _window()
    mode = _start_ui_battle(window, rng=_Rng(0.0))
    overlay = mode.overlay
    assert overlay is not None
    window.game_state_controller.state.values[POCKET_BALL_COUNT_KEY] = 0

    overlay.button_rects = {"menu:bag": (10.0, 10.0, 80.0, 30.0)}
    assert window.input_controller.on_mouse_press(20.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
    overlay.button_rects = {"capture:pocket_ball": (10.0, 10.0, 120.0, 30.0)}
    assert window.input_controller.on_mouse_press(20.0, 20.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert mode.active is True
    assert overlay.menu_state == "bag"
    assert overlay.log_line == "No Pocket Balls left!"
    assert window.game_state_controller.state.values[POCKET_BALL_COUNT_KEY] == 0


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

    _submit_first_move(window)
    submitted = overlay.snapshot()

    assert submitted["opponent_hp"] == before["opponent_hp"]
    assert submitted["presenting"] is True
    _press(window, optional_arcade.arcade.key.ENTER)
    after = overlay.snapshot()
    assert after["opponent_hp"] < before["opponent_hp"]
    assert "Sproutling used ember" in str(after["log_line"])


def test_presenting_state_holds_command_menu_until_turn_lines_drain() -> None:
    window = _window()
    mode = _start_ui_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    _submit_first_move(window)
    assert overlay.menu_state == "presenting"
    queued = len(overlay.presentation_queue)

    _press(window, optional_arcade.arcade.key.DOWN)
    _press(window, optional_arcade.arcade.key.ENTER)

    assert overlay.menu_state == "presenting"
    assert len(overlay.presentation_queue) == queued - 1
    assert mode.controller is not None
    assert len(mode.controller.turn_log) == 2


def test_dt_timer_reveals_log_lines_in_order_and_returns_menu() -> None:
    window = _window()
    mode = _start_ui_battle(window)
    overlay = mode.overlay
    assert overlay is not None
    _submit_first_move(window)

    window.ui_controller.update(0.69)
    assert overlay.log_line == "..."
    window.ui_controller.update(0.01)
    first_line = overlay.log_line
    assert "Sproutling used ember" in first_line
    window.ui_controller.update(0.70)
    second_line = overlay.log_line
    assert "Shelltide used tackle" in second_line
    window.ui_controller.update(0.70)

    assert overlay.menu_state == "root"
    assert overlay.log_line == second_line
    assert mode.active is True


def test_lethal_turn_shows_faint_line_then_ends_after_queue_drains() -> None:
    window = _window()
    mode = _start_ui_battle(window, opponent_hp=5, player_moves=("ko",))
    overlay = mode.overlay
    assert overlay is not None
    _submit_first_move(window)

    assert overlay.menu_state == "presenting"
    assert mode.active is True
    _press(window, optional_arcade.arcade.key.ENTER)
    assert "Sproutling used ko" in overlay.log_line
    assert overlay.snapshot()["opponent_hp"] == 0
    _press(window, optional_arcade.arcade.key.ENTER)
    assert overlay.log_line == "Shelltide fainted!"
    assert mode.active is True
    while mode.active:
        _press(window, optional_arcade.arcade.key.ENTER)

    assert mode.active is False
    assert window.paused is False


def test_battle_win_persists_xp_level_and_learn_lines() -> None:
    window = _window()
    starter = MonsterInstance(
        PLAYER_SPECIES,
        level=10,
        known_moves=("ko",),
        experience=xp_required_for_level(10),
    )
    values = window.game_state_controller.state.values
    values[MONSTER_PARTY_KEY] = ["starter_0001"]
    values[MONSTER_INSTANCES_KEY] = {"starter_0001": serialize_monster_instance(starter)}
    mode = _start_ui_battle(
        window,
        opponent_hp=5,
        player_moves=("ko",),
        return_context={"scene_path": "scenes/field.json", "player_instance_id": "starter_0001"},
    )
    overlay = mode.overlay
    assert overlay is not None

    _submit_first_move(window)

    row = values[MONSTER_INSTANCES_KEY]["starter_0001"]
    assert row["level"] == 11
    assert row["xp"] >= xp_required_for_level(11)
    assert "ember" in row["known_moves"]
    queued_lines = [step.line for step in overlay.presentation_queue]
    assert any("gained" in line and "XP" in line for line in queued_lines)
    assert any("grew to Lv 11" in line for line in queued_lines)
    assert any("learned ember" in line for line in queued_lines)


def test_debug_f12_launches_through_real_dispatch_when_debug_mode_enabled() -> None:
    window = _window()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = True
    window.input_controller = InputController(as_any(window))
    window.start_debug_monster_battle = MagicMock(return_value=True)
    dev_browser = types.SimpleNamespace(toggle=MagicMock())
    window.dev_browser_overlay = dev_browser

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F12,
        0,
    )

    window.start_debug_monster_battle.assert_called_once_with()
    dev_browser.toggle.assert_not_called()


def test_debug_f12_does_not_launch_when_debug_mode_disabled() -> None:
    window = _window()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = False
    window.input_controller = InputController(as_any(window))
    window.start_debug_monster_battle = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F12,
        0,
    )

    window.start_debug_monster_battle.assert_not_called()
