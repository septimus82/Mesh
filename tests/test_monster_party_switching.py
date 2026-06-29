from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.game_state_controller import GameState
from engine.input_controller import InputController
from engine.monster.battle_controller import MonsterBattleController, MoveAction
from engine.monster.battle_mode import BattleSwitchScreen, MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.collection import (
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    load_battle_party_from_values,
    serialize_monster_instance,
)
from engine.ui.menu_toolkit import MenuStackOverlay
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast


KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)
TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
MOVES = {move.id: move for move in (KO, TACKLE)}

LEAD = Species(
    id="lead",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=20),
    types=("normal",),
    learnset=("ko",),
)
BENCH = Species(
    id="bench",
    base_stats=BattleStats(hp=28, atk=18, defense=10, spd=12),
    types=("normal",),
    learnset=("tackle",),
)
FOE = Species(
    id="foe",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=1),
    types=("normal",),
    learnset=("tackle",),
)
WEAK = Species(
    id="weak",
    base_stats=BattleStats(hp=20, atk=8, defense=8, spd=4),
    types=("normal",),
    learnset=("tackle",),
)
SLOW = Species(
    id="slow",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=1),
    types=("normal",),
    learnset=("tackle",),
)
FAST = Species(
    id="fast",
    base_stats=BattleStats(hp=40, atk=20, defense=10, spd=30),
    types=("normal",),
    learnset=("ko",),
)


def _party_controller(
    *,
    lead_hp: int = 5,
    bench_hp: int = 20,
    opponent_hp: int = 30,
    opponent_move: str = "tackle",
) -> MonsterBattleController:
    lead = MonsterInstance(LEAD, level=10, current_hp=lead_hp, known_moves=("ko",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=bench_hp, known_moves=("tackle",))
    opponent = MonsterInstance(FOE, level=10, current_hp=opponent_hp, known_moves=(opponent_move,))
    return MonsterBattleController(
        player=lead,
        opponent=opponent,
        player_party=[lead, bench_mon],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", opponent_move),
    )


def _window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = UIController(as_any(window))
    window.input_controller = InputController(as_any(window))
    window.game_state_controller = types.SimpleNamespace(state=GameState())
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    return window


def test_faint_with_bench_enters_must_switch_not_lost() -> None:
    lead = MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("tackle",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=20, known_moves=("tackle",))
    opponent = MonsterInstance(FAST, level=10, current_hp=40, known_moves=("ko",))
    controller = MonsterBattleController(
        player=lead,
        opponent=opponent,
        player_party=[lead, bench_mon],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "ko"),
    )

    result = controller.submit_action("player", "tackle")

    assert result is None
    assert controller.phase == "must_switch"
    assert controller.player.fainted is True
    assert controller.opponent.fainted is False
    assert controller.result is None


def test_switch_after_faint_continues_battle() -> None:
    lead = MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("tackle",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=20, known_moves=("tackle",))
    opponent = MonsterInstance(FAST, level=10, current_hp=40, known_moves=("ko",))
    controller = MonsterBattleController(
        player=lead,
        opponent=opponent,
        player_party=[lead, bench_mon],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "ko"),
    )
    controller.submit_action("player", "tackle")
    assert controller.phase == "must_switch"

    result = controller.submit_switch(1)

    assert result is None
    assert controller.phase == "choose_action"
    assert controller.active_index == 1
    assert controller.player.species.id == "bench"
    assert controller.player.fainted is False
    assert controller.opponent.fainted is False


def test_faint_with_empty_bench_is_lost() -> None:
    lead = MonsterInstance(WEAK, level=5, current_hp=5, known_moves=("tackle",))
    foe = MonsterInstance(FOE, level=10, current_hp=30, known_moves=("ko",))
    controller = MonsterBattleController(
        player=lead,
        opponent=foe,
        player_party=[lead],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "ko"),
    )

    result = controller.submit_action("player", "tackle")

    assert result is not None
    assert result.outcome == "lost"
    assert controller.phase == "lost"


def test_voluntary_switch_costs_turn_and_opponent_acts() -> None:
    lead = MonsterInstance(LEAD, level=10, current_hp=20, known_moves=("tackle",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=18, known_moves=("tackle",))
    opponent = MonsterInstance(FOE, level=10, current_hp=30, known_moves=("tackle",))
    controller = MonsterBattleController(
        player=lead,
        opponent=opponent,
        player_party=[lead, bench_mon],
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    turn_before = controller.turn_number

    result = controller.submit_switch(1)

    assert result is None
    assert controller.active_index == 1
    assert controller.phase == "choose_action"
    assert controller.turn_number == turn_before + 1
    kinds = [entry.kind for entry in controller.turn_log]
    assert kinds.count("switch") == 2
    assert any(entry.kind == "move" and entry.side == "opponent" for entry in controller.turn_log)


def test_win_when_opponent_faints_with_bench_remaining() -> None:
    controller = _party_controller(lead_hp=20, bench_hp=20, opponent_hp=5)

    result = controller.submit_action("player", "ko")

    assert result is not None
    assert result.outcome == "won"
    assert controller.player.fainted is False
    assert any(not monster.fainted for monster in controller.player_party[1:])


def test_single_monster_party_behaves_like_old_1v1() -> None:
    lead = MonsterInstance(WEAK, level=5, current_hp=5, known_moves=("tackle",))
    foe = MonsterInstance(FOE, level=10, current_hp=30, known_moves=("ko",))
    controller = MonsterBattleController(
        player=lead,
        opponent=foe,
        moves=MOVES,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "ko"),
    )

    result = controller.submit_action("player", "tackle")

    assert result is not None
    assert result.outcome == "lost"
    assert controller.phase == "lost"
    assert len(controller.player_party) == 1


def test_load_battle_party_from_game_state() -> None:
    values = {
        MONSTER_PARTY_KEY: ["a", "b"],
        MONSTER_INSTANCES_KEY: {
            "a": serialize_monster_instance(MonsterInstance(LEAD, level=4, current_hp=12, known_moves=("tackle",))),
            "b": serialize_monster_instance(MonsterInstance(BENCH, level=3, current_hp=10, known_moves=("tackle",))),
        },
    }
    fallback = MonsterInstance(WEAK, level=1, known_moves=("tackle",))
    species = {"lead": LEAD, "bench": BENCH}

    party = load_battle_party_from_values(values, species, fallback=fallback)

    assert len(party) == 2
    assert party[0].species.id == "lead"
    assert party[0].level == 4
    assert party[1].species.id == "bench"


def test_load_battle_party_falls_back_when_empty() -> None:
    values = {MONSTER_PARTY_KEY: [], MONSTER_INSTANCES_KEY: {}}
    fallback = MonsterInstance(WEAK, level=7, known_moves=("tackle",))

    party = load_battle_party_from_values(values, {"weak": WEAK}, fallback=fallback)

    assert len(party) == 1
    assert party[0].level == 7


def test_switch_screen_disables_fainted_and_active_monsters() -> None:
    window = _window()
    mode = MonsterBattleMode(as_any(window))
    lead = MonsterInstance(LEAD, level=10, current_hp=0, known_moves=("ko",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=18, known_moves=("tackle",))
    mode.controller = MonsterBattleController(
        player=lead,
        opponent=MonsterInstance(FOE, level=10, current_hp=1, known_moves=("tackle",)),
        player_party=[lead, bench_mon],
        moves=MOVES,
    )
    mode.controller.phase = "must_switch"
    mode.active = True
    screen = BattleSwitchScreen(mode, forced=True)

    assert screen.items[0].enabled is False
    assert screen.items[1].enabled is True


def test_forced_switch_screen_blocks_escape() -> None:
    window = _window()
    stack = MenuStackOverlay(as_any(window))
    mode = MonsterBattleMode(as_any(window))
    lead = MonsterInstance(LEAD, level=10, current_hp=0, known_moves=("ko",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=18, known_moves=("tackle",))
    mode.controller = MonsterBattleController(
        player=lead,
        opponent=MonsterInstance(FOE, level=10, current_hp=0, known_moves=("tackle",)),
        player_party=[lead, bench_mon],
        moves=MOVES,
    )
    mode.active = True
    screen = BattleSwitchScreen(mode, forced=True)
    stack.push(screen)
    before = len(stack.screens)

    assert screen.on_key_press(optional_arcade.arcade.key.ESCAPE, 0, stack) is True
    assert len(stack.screens) == before


def test_voluntary_switch_screen_allows_escape() -> None:
    window = _window()
    stack = MenuStackOverlay(as_any(window))
    mode = MonsterBattleMode(as_any(window))
    lead = MonsterInstance(LEAD, level=10, current_hp=20, known_moves=("tackle",))
    bench_mon = MonsterInstance(BENCH, level=8, current_hp=18, known_moves=("tackle",))
    mode.controller = MonsterBattleController(
        player=lead,
        opponent=MonsterInstance(FOE, level=10, current_hp=30, known_moves=("tackle",)),
        player_party=[lead, bench_mon],
        moves=MOVES,
    )
    mode.active = True
    screen = BattleSwitchScreen(mode, forced=False)
    stack.push(screen)

    assert screen.on_key_press(optional_arcade.arcade.key.ESCAPE, 0, stack) is True
    assert stack.screens == []
