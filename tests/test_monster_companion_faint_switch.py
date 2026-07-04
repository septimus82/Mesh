from __future__ import annotations

import random
import types
from dataclasses import replace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from engine.game_state_controller import GameState
from engine.input_controller import InputController
from engine.monster.battle_controller import BattleResult, MonsterBattleController, MoveAction
from engine.monster.battle_mode import MONSTER_BATTLE_RESULT_KEY, MonsterBattleMode, MonsterBattleOverlay
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.collection import (
    COMPANION_MIND_INSTANCE_KEY,
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    ensure_monster_collection,
    load_companion_mind_for_instance,
    serialize_monster_instance,
)
from engine.monster.companion_mind import (
    ATTACK,
    CompanionMind,
    LearnedWeights,
    Temperament,
    companion_mind_to_dict,
    praise,
)
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast

KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)
TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
MOVES = {move.id: move for move in (KO, TACKLE)}

LEAD = Species(
    id="lead",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=1),
    types=("normal",),
    learnset=("tackle",),
)
BENCH = Species(
    id="bench",
    base_stats=BattleStats(hp=28, atk=18, defense=10, spd=12),
    types=("normal",),
    learnset=("tackle",),
)
FOE = Species(
    id="foe",
    base_stats=BattleStats(hp=30, atk=20, defense=10, spd=30),
    types=("normal",),
    learnset=("ko",),
)


def _window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.game_over = False
    window.show_debug = False
    window.monster_battle_mode_active = False
    window.ui_controller = UIController(as_any(window))
    window.input_controller = InputController(as_any(window))
    window.game_state_controller = types.SimpleNamespace(state=GameState())
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    return window


def _drain_presentations(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    for _ in range(40):
        progressed = False
        while overlay.menu_state == "presenting":
            overlay._advance_presentation()
            progressed = True
        if mode.controller is None or mode.controller.result is not None:
            return
        if (
            mode.companion_awaiting_reinforcement
            and mode.controller is not None
            and mode.controller.phase == "choose_action"
            and not mode.controller.player.fainted
        ):
            return
        if not progressed:
            return


def _opponent_ko_active_only(controller: MonsterBattleController) -> MoveAction:
    if controller.active_index == 0:
        return MoveAction("opponent", "ko")
    return MoveAction("opponent", "tackle")


def _start_companion_party_battle(
    window: types.SimpleNamespace,
    *,
    lead_hp: int = 5,
    bench_hp: int = 20,
    party_size: int = 2,
) -> MonsterBattleMode:
    values = window.game_state_controller.state.values
    ensure_monster_collection(values)
    lead = MonsterInstance(LEAD, level=10, current_hp=lead_hp, known_moves=("tackle",))
    lead_mind = CompanionMind(
        temperament=Temperament(aggression=55.0, fear=10.0),
        learned=LearnedWeights(),
        trust=60.0,
        bond=40.0,
    )
    bench_mind = CompanionMind(
        temperament=Temperament(aggression=40.0, fear=8.0),
        learned=LearnedWeights(),
        trust=72.0,
        bond=45.0,
    )
    party: list[MonsterInstance] = [lead]
    instance_ids: list[str] = ["lead_0001"]
    rows: dict[str, dict[str, object]] = {
        "lead_0001": {
            **serialize_monster_instance(lead),
            COMPANION_MIND_INSTANCE_KEY: companion_mind_to_dict(lead_mind),
        },
    }
    if party_size > 1:
        bench = MonsterInstance(BENCH, level=8, current_hp=bench_hp, known_moves=("tackle",))
        party.append(bench)
        instance_ids.append("bench_0001")
        rows["bench_0001"] = {
            **serialize_monster_instance(bench),
            COMPANION_MIND_INSTANCE_KEY: companion_mind_to_dict(bench_mind),
        }
    values[MONSTER_PARTY_KEY] = list(instance_ids)
    values[MONSTER_INSTANCES_KEY] = rows

    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=party[0],
        player_party=party,
        player_party_instance_ids=instance_ids,
        opponent_monster=MonsterInstance(FOE, level=10, current_hp=50, known_moves=("ko",)),
        moves=MOVES,
        companion_mode=True,
        companion_mind=lead_mind,
        rng=random.Random(0),
        opponent_action_provider=_opponent_ko_active_only if party_size > 1 else (lambda _c: MoveAction("opponent", "ko")),
    )
    return mode


def test_companion_faint_with_bench_auto_switches_and_battle_continues() -> None:
    window = _window()
    mode = _start_companion_party_battle(window)

    _drain_presentations(mode)

    assert mode.controller is not None
    assert mode.controller.result is None
    assert mode.controller.phase == "choose_action"
    assert mode.controller.active_index == 1
    assert mode.controller.player.species.id == "bench"
    assert mode.controller.player.fainted is False
    assert mode.controller.player.current_hp > 0
    assert mode.companion_awaiting_reinforcement is True
    assert mode.companion_mind is not None
    assert mode.companion_mind.trust == pytest.approx(72.0)
    assert mode.companion_mind.bond == pytest.approx(45.0)
    labels = [label for _, label in mode.overlay._current_actions()]
    assert labels == ["Praise", "Scold", "Wait", "Ball"]


def test_companion_faint_without_bench_ends_lost() -> None:
    window = _window()
    mode = _start_companion_party_battle(window, party_size=1)

    _drain_presentations(mode)

    assert mode.controller is None
    values = window.game_state_controller.state.values

    assert values[MONSTER_BATTLE_RESULT_KEY]["outcome"] == "lost"
    assert mode.active is False


def test_companion_bench_mind_is_loaded_and_persisted_on_battle_end() -> None:
    window = _window()
    mode = _start_companion_party_battle(window)
    values = window.game_state_controller.state.values

    _drain_presentations(mode)
    assert mode.companion_mind is not None
    mode.companion_mind = praise(replace(mode.companion_mind, last_behavior=ATTACK))
    trained_trust = mode.companion_mind.trust

    mode.end_battle(
        BattleResult(cast(Any, "won"), winning_side="player", losing_side="opponent", turns=mode.controller.turn_number),
    )

    restored = load_companion_mind_for_instance(values, "bench_0001")
    assert restored is not None
    assert restored.trust == pytest.approx(trained_trust)


def test_command_battler_must_switch_still_opens_switch_screen() -> None:
    window = _window()
    mode = MonsterBattleMode(as_any(window))
    mode.companion_mode = False
    mode.active = True
    lead = MonsterInstance(LEAD, level=10, current_hp=0, known_moves=("tackle",))
    bench = MonsterInstance(BENCH, level=8, current_hp=18, known_moves=("tackle",))
    mode.controller = MonsterBattleController(
        player=lead,
        opponent=MonsterInstance(FOE, level=10, current_hp=30, known_moves=("tackle",)),
        player_party=[lead, bench],
        moves=MOVES,
    )
    mode.controller.phase = "must_switch"
    mode.open_switch_screen = MagicMock()
    overlay = MonsterBattleOverlay(as_any(window), mode)

    overlay._finish_presentation()

    mode.open_switch_screen.assert_called_once_with(forced=True)


def test_companion_must_switch_auto_sends_bench_without_switch_screen() -> None:
    window = _window()
    mode = _start_companion_party_battle(window)
    mode.open_switch_screen = MagicMock()
    overlay = mode.overlay
    assert overlay is not None

    while overlay.menu_state == "presenting":
        overlay._advance_presentation()

    mode.open_switch_screen.assert_not_called()
    assert mode.controller is not None
    assert mode.controller.phase == "choose_action"
    assert mode.controller.active_index == 1
