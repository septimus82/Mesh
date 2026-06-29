from __future__ import annotations

import importlib
import random
from pathlib import Path

import pytest

from engine.monster.battle_controller import (
    InvalidBattleActionError,
    MonsterBattleController,
    MoveAction,
    controller_from_catalog,
)
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.data_load import load_monster_catalog

pytestmark = pytest.mark.fast


TYPE_CHART = {
    "fire": {"grass": 2.0, "water": 0.5},
    "grass": {"water": 2.0, "fire": 0.5},
}

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)
UNRELIABLE = Move(id="unreliable", type="normal", power=40, accuracy=90, pp=10)

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
SPROUT = Species(
    id="sprout",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
    types=("grass",),
    learnset=("tackle", "ember"),
)
TURTLE = Species(
    id="turtle",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)


def _controller(
    *,
    player: MonsterInstance | None = None,
    opponent: MonsterInstance | None = None,
    rng: random.Random | None = None,
    opponent_move_id: str = "tackle",
) -> MonsterBattleController:
    return MonsterBattleController(
        player=player or MonsterInstance(SPROUT, level=10, known_moves=("tackle", "ember")),
        opponent=opponent or MonsterInstance(TURTLE, level=10, known_moves=("tackle",)),
        moves={move.id: move for move in (TACKLE, EMBER, KO, UNRELIABLE)},
        type_chart=TYPE_CHART,
        rng=rng,
        opponent_action_provider=lambda _controller: MoveAction("opponent", opponent_move_id),
    )


def test_controller_imports_without_runtime_initialization() -> None:
    module = importlib.import_module("engine.monster.battle_controller")
    assert module.__name__ == "engine.monster.battle_controller"
    assert not hasattr(module, "GameWindow")


def test_fresh_controller_starts_in_choose_action_phase() -> None:
    controller = _controller()

    assert controller.phase == "choose_action"
    assert controller.turn_number == 1
    assert controller.result is None
    assert controller.turn_log == []


def test_submit_move_when_both_survive_returns_to_choose_action() -> None:
    controller = _controller()

    result = controller.submit_action("player", "tackle")

    assert result is None
    assert controller.phase == "choose_action"
    assert controller.turn_number == 2
    assert [entry.side for entry in controller.turn_log] == ["player", "opponent"]
    assert controller.player.current_hp < controller.player.stats.hp
    assert controller.opponent.current_hp < controller.opponent.stats.hp


def test_lethal_player_turn_ends_with_won_outcome() -> None:
    controller = _controller(
        player=MonsterInstance(FAST, level=10, current_hp=10, known_moves=("ko",)),
        opponent=MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("ko",)),
        opponent_move_id="ko",
    )

    result = controller.submit_action("player", "ko")

    assert result is not None
    assert result.outcome == "won"
    assert result.winning_side == "player"
    assert controller.phase == "won"
    assert controller.opponent.fainted is True


def test_lethal_opponent_turn_ends_with_lost_outcome() -> None:
    controller = _controller(
        player=MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("ko",)),
        opponent=MonsterInstance(FAST, level=10, current_hp=10, known_moves=("ko",)),
        opponent_move_id="ko",
    )

    result = controller.submit_action("player", "ko")

    assert result is not None
    assert result.outcome == "lost"
    assert result.winning_side == "opponent"
    assert controller.phase == "lost"
    assert controller.player.fainted is True


def test_speed_order_prevents_fainted_slower_monster_from_retaliating() -> None:
    fast_player = _controller(
        player=MonsterInstance(FAST, level=10, current_hp=5, known_moves=("ko",)),
        opponent=MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("ko",)),
        opponent_move_id="ko",
    )
    slow_player = _controller(
        player=MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("ko",)),
        opponent=MonsterInstance(FAST, level=10, current_hp=5, known_moves=("ko",)),
        opponent_move_id="ko",
    )

    fast_player.submit_action("player", "ko")
    slow_player.submit_action("player", "ko")

    assert [entry.side for entry in fast_player.turn_log] == ["player"]
    assert fast_player.result is not None
    assert fast_player.result.outcome == "won"
    assert [entry.side for entry in slow_player.turn_log] == ["opponent"]
    assert slow_player.result is not None
    assert slow_player.result.outcome == "lost"


def test_action_submitted_in_wrong_phase_is_rejected_without_mutation() -> None:
    controller = _controller(
        player=MonsterInstance(FAST, level=10, current_hp=10, known_moves=("ko",)),
        opponent=MonsterInstance(SLOW, level=10, current_hp=5, known_moves=("ko",)),
        opponent_move_id="ko",
    )
    controller.submit_action("player", "ko")
    before = controller.snapshot()

    with pytest.raises(InvalidBattleActionError):
        controller.submit_action("player", "ko")

    assert controller.snapshot() == before


def test_same_seed_and_actions_produce_identical_trajectory() -> None:
    first = _controller(rng=random.Random(1234), opponent_move_id="unreliable")
    second = _controller(rng=random.Random(1234), opponent_move_id="unreliable")

    first.submit_action("player", "unreliable")
    first.submit_action("player", "unreliable")
    second.submit_action("player", "unreliable")
    second.submit_action("player", "unreliable")

    assert first.snapshot() == second.snapshot()


def test_controller_can_be_built_from_monster_catalog() -> None:
    data_dir = Path("assets/data")
    catalog, validation = load_monster_catalog(data_dir)
    assert validation.ok is True
    assert catalog is not None

    controller = controller_from_catalog(
        catalog,
        player=MonsterInstance(catalog.species["sproutling"], level=10, known_moves=("tackle",)),
        opponent=MonsterInstance(catalog.species["shelltide"], level=10, known_moves=("tackle",)),
        opponent_action_provider=lambda _controller: "tackle",
    )

    controller.submit_action("player", "tackle")

    assert controller.phase == "choose_action"
    assert len(controller.turn_log) == 2
