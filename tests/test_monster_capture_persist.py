from __future__ import annotations

import types
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.game_state_controller import GameState
from engine.monster.battle_controller import MoveAction
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.collection import (
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    POCKET_BALL_COUNT_KEY,
    serialize_monster_instance,
)
from tests._typing import as_any

pytestmark = pytest.mark.fast


TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
KO = Move(id="ko", type="normal", power=500, accuracy=100, pp=5)

PLAYER_SPECIES = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=12, defense=10, spd=20),
    types=("grass",),
    learnset=("tackle",),
)
OPPONENT_SPECIES = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


def _window(*, values: dict[str, Any] | None = None) -> types.SimpleNamespace:
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
    state = GameState()
    if values is not None:
        state.values = values
    window.game_state_controller = types.SimpleNamespace(state=state)
    return window


def _start_battle(
    window: types.SimpleNamespace,
    *,
    player: MonsterInstance,
    player_party: list[MonsterInstance],
    player_party_instance_ids: list[str | None],
    opponent: MonsterInstance,
    rng: _Rng | None = None,
) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=player,
        player_party=player_party,
        player_party_instance_ids=player_party_instance_ids,
        opponent_monster=opponent,
        moves={TACKLE.id: TACKLE, KO.id: KO},
        rng=rng,
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _finish_capture_presentation(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()


def test_empty_party_capture_persists_caught_species_once() -> None:
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: [],
        MONSTER_INSTANCES_KEY: {},
        POCKET_BALL_COUNT_KEY: 3,
    }
    window = _window(values=values)
    fallback = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",))
    opponent = MonsterInstance(OPPONENT_SPECIES, level=6, current_hp=20, known_moves=("tackle",))
    mode = _start_battle(
        window,
        player=fallback,
        player_party=[fallback],
        player_party_instance_ids=[None],
        opponent=opponent,
        rng=_Rng(0.0),
    )

    capture = mode.attempt_capture(item_id="pocket_ball")
    assert capture is not None
    assert capture.caught is True
    _finish_capture_presentation(mode)

    assert mode.active is False
    party = values[MONSTER_PARTY_KEY]
    assert len(party) == 1
    caught_id = str(party[0])
    caught_row = values[MONSTER_INSTANCES_KEY][caught_id]
    assert caught_row["species_id"] == "shelltide"
    assert caught_row["level"] == 6


def test_nonempty_party_capture_does_not_clobber_caught_instance() -> None:
    player_row = serialize_monster_instance(MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",)))
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: ["sproutling_0001"],
        MONSTER_INSTANCES_KEY: {"sproutling_0001": dict(player_row)},
        POCKET_BALL_COUNT_KEY: 3,
    }
    window = _window(values=values)
    player = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=18, known_moves=("tackle",))
    opponent = MonsterInstance(OPPONENT_SPECIES, level=6, current_hp=20, known_moves=("tackle",))
    mode = _start_battle(
        window,
        player=player,
        player_party=[player],
        player_party_instance_ids=["sproutling_0001"],
        opponent=opponent,
        rng=_Rng(0.0),
    )

    capture = mode.attempt_capture(item_id="pocket_ball")
    assert capture is not None
    assert capture.caught is True
    _finish_capture_presentation(mode)

    party = values[MONSTER_PARTY_KEY]
    assert party[0] == "sproutling_0001"
    caught_id = str(party[1])
    assert values[MONSTER_INSTANCES_KEY][caught_id]["species_id"] == "shelltide"
    assert values[MONSTER_INSTANCES_KEY]["sproutling_0001"]["species_id"] == "sproutling"


def test_win_without_capture_persists_player_party_hp() -> None:
    player_row = serialize_monster_instance(MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",)))
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: ["sproutling_0001"],
        MONSTER_INSTANCES_KEY: {"sproutling_0001": dict(player_row)},
        POCKET_BALL_COUNT_KEY: 3,
    }
    window = _window(values=values)
    player = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("ko",))
    opponent = MonsterInstance(OPPONENT_SPECIES, level=6, current_hp=5, known_moves=("tackle",))
    mode = _start_battle(
        window,
        player=player,
        player_party=[player],
        player_party_instance_ids=["sproutling_0001"],
        opponent=opponent,
    )

    result = mode.controller.submit_action("player", "ko")
    assert result is not None
    assert result.outcome == "won"
    damaged = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=11, known_moves=("ko",))
    mode.controller._set_monster("player", damaged)
    mode.end_battle(result)

    row = values[MONSTER_INSTANCES_KEY]["sproutling_0001"]
    assert row["species_id"] == "sproutling"
    assert int(row["current_hp"]) == 11
    assert len(values[MONSTER_PARTY_KEY]) == 1
