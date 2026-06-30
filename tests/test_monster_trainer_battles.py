from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import load_config
from engine.game_runtime import input_dispatch
from engine.game_state_controller import GameState
from engine.input_controller import InputController
from engine.monster.battle_controller import MonsterBattleController, MoveAction
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from tests._typing import as_any

pytestmark = pytest.mark.fast


KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)
TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
MOVES = {move.id: move for move in (KO, TACKLE)}

FAST = Species(
    id="fast",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=30),
    types=("normal",),
    learnset=("ko",),
)
SLOW = Species(
    id="slow",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=1),
    types=("normal",),
    learnset=("ko",),
)
LEAD = Species(
    id="lead",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=8),
    types=("normal",),
    learnset=("tackle",),
)
BENCH = Species(
    id="bench",
    base_stats=BattleStats(hp=28, atk=18, defense=10, spd=6),
    types=("normal",),
    learnset=("tackle",),
)
PLAYER = Species(
    id="player",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("ko",),
)


def _trainer_controller(
    *,
    lead_hp: int = 5,
    bench_hp: int = 20,
    player_hp: int = 30,
) -> MonsterBattleController:
    lead = MonsterInstance(LEAD, level=10, current_hp=lead_hp, known_moves=("tackle",))
    bench = MonsterInstance(BENCH, level=8, current_hp=bench_hp, known_moves=("tackle",))
    player = MonsterInstance(PLAYER, level=10, current_hp=player_hp, known_moves=("ko",))
    return MonsterBattleController(
        player=player,
        opponent=lead,
        opponent_party=[lead, bench],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )


def _window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = types.SimpleNamespace(
        ui_elements=[],
        register_ui_element=lambda element: window.ui_controller.ui_elements.append(element),
    )
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    window.game_state_controller = types.SimpleNamespace(state=GameState())
    return window


def test_opponent_faint_with_bench_auto_switches_and_battle_continues() -> None:
    controller = _trainer_controller(lead_hp=5, bench_hp=20)

    result = controller.submit_action("player", "ko")

    assert result is None
    assert controller.phase == "choose_action"
    assert controller.opponent.species.id == "bench"
    assert controller.opponent_active_index == 1
    assert controller.opponent_party[0].fainted is True
    switch_entries = [entry for entry in controller.turn_log if entry.kind == "switch"]
    assert len(switch_entries) == 1
    assert switch_entries[0].side == "opponent"
    assert switch_entries[0].party_index == 1


def test_opponent_whole_party_fainted_is_won() -> None:
    controller = _trainer_controller(lead_hp=5, bench_hp=5)

    first = controller.submit_action("player", "ko")
    assert first is None
    assert controller.phase == "choose_action"

    result = controller.submit_action("player", "ko")

    assert result is not None
    assert result.outcome == "won"
    assert controller.phase == "won"
    assert all(monster.fainted for monster in controller.opponent_party)


def test_single_opponent_behaves_like_legacy_battle() -> None:
    controller = MonsterBattleController(
        player=MonsterInstance(FAST, level=10, current_hp=10, known_moves=("ko",)),
        opponent=MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("ko",)),
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "ko"),
    )

    result = controller.submit_action("player", "ko")

    assert result is not None
    assert result.outcome == "won"
    assert len(controller.opponent_party) == 1
    assert controller.turn_log[-1].kind == "move"


def test_player_must_switch_coexists_with_opponent_party() -> None:
    lead = MonsterInstance(LEAD, level=10, current_hp=30, known_moves=("ko",))
    bench = MonsterInstance(BENCH, level=8, current_hp=20, known_moves=("tackle",))
    player = MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("tackle",))
    player_bench = MonsterInstance(PLAYER, level=8, current_hp=18, known_moves=("tackle",))
    controller = MonsterBattleController(
        player=player,
        opponent=lead,
        player_party=[player, player_bench],
        opponent_party=[lead, bench],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "ko"),
    )

    result = controller.submit_action("player", "tackle")

    assert result is None
    assert controller.phase == "must_switch"
    assert controller.player.fainted is True
    assert controller.opponent.fainted is False


def test_opponent_auto_switch_picks_next_non_fainted_in_order() -> None:
    lead = MonsterInstance(LEAD, level=10, current_hp=5, known_moves=("tackle",))
    middle = MonsterInstance(BENCH, level=8, current_hp=0, known_moves=("tackle",))
    back = MonsterInstance(
        Species(
            id="back",
            base_stats=BattleStats(hp=26, atk=16, defense=10, spd=5),
            types=("normal",),
            learnset=("tackle",),
        ),
        level=7,
        current_hp=16,
        known_moves=("tackle",),
    )
    player = MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("ko",))
    controller = MonsterBattleController(
        player=player,
        opponent=lead,
        opponent_party=[lead, middle, back],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )

    controller.submit_action("player", "ko")

    assert controller.opponent_active_index == 2
    assert controller.opponent.species.id == "back"


def test_trainer_presentation_includes_foe_faint_and_sent_out_lines() -> None:
    window = _window()
    mode = MonsterBattleMode(as_any(window))
    lead = MonsterInstance(LEAD, level=10, current_hp=5, known_moves=("tackle",))
    bench = MonsterInstance(BENCH, level=8, current_hp=20, known_moves=("tackle",))
    player = MonsterInstance(PLAYER, level=10, current_hp=30, known_moves=("ko",))
    mode.controller = MonsterBattleController(
        player=player,
        opponent=lead,
        opponent_party=[lead, bench],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    mode.active = True

    before_len = len(mode.controller.turn_log)
    mode.controller.submit_action("player", "ko")
    steps = mode._build_presentation_steps(before_len, 30, 5)
    lines = [step.line for step in steps]

    assert any("Foe Lead fainted!" in line for line in lines)
    assert any("Trainer sent out Bench!" in line for line in lines)


class _Console:
    active = False

    def process_key(self, _key: int, _modifiers: int) -> bool:
        return False


def test_f7_launches_trainer_battle_when_debug_mode_enabled() -> None:
    window = types.SimpleNamespace()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = True
    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)
    window.ui_controller = types.SimpleNamespace(on_key_press=lambda _key, _mods: False)
    window.input_controller = InputController(as_any(window))
    window.start_debug_trainer_monster_battle = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F7,
        0,
    )

    window.start_debug_trainer_monster_battle.assert_called_once_with()


def test_f7_does_not_launch_trainer_battle_when_debug_mode_disabled() -> None:
    window = types.SimpleNamespace()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = False
    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)
    window.ui_controller = types.SimpleNamespace(on_key_press=lambda _key, _mods: False)
    window.input_controller = InputController(as_any(window))
    window.game_over = False
    window.show_debug = False
    window.start_debug_trainer_monster_battle = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F7,
        0,
    )

    window.start_debug_trainer_monster_battle.assert_not_called()


def test_f12_launches_wild_battle_when_debug_mode_enabled() -> None:
    window = types.SimpleNamespace()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = True
    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)
    window.ui_controller = types.SimpleNamespace(on_key_press=lambda _key, _mods: False)
    window.input_controller = InputController(as_any(window))
    window.game_over = False
    window.start_debug_monster_battle = MagicMock(return_value=True)
    window.start_debug_trainer_monster_battle = MagicMock(return_value=True)

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.F12, 0)

    window.start_debug_monster_battle.assert_called_once_with()
    window.start_debug_trainer_monster_battle.assert_not_called()
