from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from engine.events import MeshEventBus
from engine.game_runtime.tick import on_update
from engine.game_state_controller import GameState
from engine.monster.battle_controller import BattleResult, MoveAction
from engine.monster.battle_mode import (
    MONSTER_BATTLE_ENDED_EVENT,
    MONSTER_BATTLE_RESULT_KEY,
    MONSTER_BATTLE_RETURN_CONTEXT_KEY,
    MonsterBattleMode,
)
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast


TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)

PLAYER_SPECIES = Species(
    id="player_mon",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("tackle", "ko"),
)
OPPONENT_SPECIES = Species(
    id="opponent_mon",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=5),
    types=("normal",),
    learnset=("tackle",),
)


class _Input:
    def was_action_pressed(self, _action: str) -> bool:
        return False

    def is_key_down(self, _key: int) -> bool:
        return False


def _fake_window(*, paused: bool = False, game_over: bool = False):
    window = types.SimpleNamespace()
    window.paused = paused
    window.game_over = game_over
    window.monster_battle_mode_active = False
    window.input_controller = types.SimpleNamespace(update=MagicMock())
    window.input = _Input()
    window.asset_hot_reload_watcher = None
    window.audio = None
    window.scene_controller = types.SimpleNamespace(update=MagicMock())
    window.particle_manager = types.SimpleNamespace(update=MagicMock())
    window.lighting = None
    window.day_night = None
    window.ui_controller = UIController(as_any(window))
    window.game_state_controller = types.SimpleNamespace(state=GameState(), update=MagicMock(), handle_event=MagicMock())
    window.event_bus = MeshEventBus()
    window._mesh_event_queue = []
    window.consume_events = MagicMock(return_value=[])
    window._debug_print_events = MagicMock()
    window.request_scene_reload = MagicMock()
    window.game_over_screen = types.SimpleNamespace(visible=True)
    return window


def _start_mode(window, *, prior_pause: bool | None = None) -> MonsterBattleMode:
    if prior_pause is not None:
        window.paused = prior_pause
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=MonsterInstance(PLAYER_SPECIES, level=10, known_moves=("ko",)),
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, current_hp=5, known_moves=("tackle",)),
        moves={TACKLE.id: TACKLE, KO.id: KO},
        return_context={"scene_path": "scenes/field.json", "encounter_id": "test_encounter"},
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def test_starting_battle_mode_pauses_overworld_but_ui_still_updates() -> None:
    window = _fake_window(paused=False)
    mode = _start_mode(window)
    assert mode.active is True
    assert window.paused is True
    update_ui = MagicMock(wraps=window.ui_controller.update)
    window.ui_controller.update = update_ui

    on_update(as_any(window), 0.016)

    window.scene_controller.update.assert_not_called()
    update_ui.assert_called_once_with(0.016)
    assert len(window.ui_controller.ui_elements) == 1


def test_battle_overlay_blocks_gameplay_input() -> None:
    window = _fake_window(paused=False)
    mode = _start_mode(window)

    assert mode.overlay is not None
    assert mode.overlay.blocks_input is True
    assert window.ui_controller.input_blocked is True


def test_end_battle_clears_mode_applies_result_emits_event_and_restores_pause() -> None:
    window = _fake_window(paused=True)
    seen_events = []
    window.event_bus.subscribe(MONSTER_BATTLE_ENDED_EVENT, seen_events.append)
    mode = _start_mode(window, prior_pause=True)

    result = BattleResult("won", winning_side="player", losing_side="opponent", turns=1)
    returned = mode.end_battle(result)

    assert returned == result
    assert mode.active is False
    assert mode.controller is None
    assert mode.overlay is None
    assert window.monster_battle_mode_active is False
    assert window.paused is True
    assert window.ui_controller.input_blocked is False
    values = window.game_state_controller.state.values
    assert values[MONSTER_BATTLE_RESULT_KEY]["outcome"] == "won"
    assert values[MONSTER_BATTLE_RETURN_CONTEXT_KEY]["encounter_id"] == "test_encounter"
    assert len(seen_events) == 1
    assert seen_events[0].payload["outcome"] == "won"


def test_end_battle_restores_unpaused_prior_state() -> None:
    window = _fake_window(paused=False)
    mode = _start_mode(window, prior_pause=False)

    mode.end_battle(BattleResult("won", winning_side="player", losing_side="opponent", turns=1))

    assert window.paused is False
    assert window.ui_controller.ui_elements == []


def test_mode_does_not_corrupt_normal_tick_branch_after_exit() -> None:
    window = _fake_window(paused=False)
    mode = _start_mode(window, prior_pause=False)
    mode.end_battle(BattleResult("won", winning_side="player", losing_side="opponent", turns=1))

    on_update(as_any(window), 0.016)

    window.scene_controller.update.assert_called_once_with(0.016)
    window.game_state_controller.update.assert_called_once_with(0.016)


def test_game_over_tick_branch_still_returns_before_scene_and_ui_update() -> None:
    window = _fake_window(paused=False, game_over=True)

    on_update(as_any(window), 0.016)

    window.scene_controller.update.assert_not_called()
    assert len(window.ui_controller.ui_elements) == 0
    window.request_scene_reload.assert_not_called()
