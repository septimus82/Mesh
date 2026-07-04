"""Companion-mode capture from reinforcement menu (SPIKE-CATCH)."""

from __future__ import annotations

import random
import types
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from engine import savegame
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
    capture_rate=255,
)
HARD_TO_CATCH = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
    capture_rate=10,
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


def _start_companion_battle(
    window: types.SimpleNamespace,
    *,
    return_context: dict[str, Any] | None = None,
    opponent_party: list[MonsterInstance] | None = None,
    opponent_species: Species = OPPONENT_SPECIES,
    rng: _Rng | random.Random | None = None,
) -> MonsterBattleMode:
    player_row = serialize_monster_instance(
        MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",)),
    )
    values = window.game_state_controller.state.values
    values.setdefault(MONSTER_PARTY_KEY, ["sproutling_0001"])
    values.setdefault(MONSTER_INSTANCES_KEY, {"sproutling_0001": dict(player_row)})
    values.setdefault(POCKET_BALL_COUNT_KEY, 3)

    player = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",))
    opponent = MonsterInstance(opponent_species, level=6, current_hp=20, known_moves=("tackle",))
    if opponent_party is None:
        opponent_party = [opponent]
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=player,
        player_party=[player],
        player_party_instance_ids=["sproutling_0001"],
        opponent_monster=opponent_party[0],
        opponent_party=opponent_party,
        moves={TACKLE.id: TACKLE},
        companion_mode=True,
        return_context=return_context or {"source": "companion_encounter_zone"},
        rng=rng or random.Random(0),
        opponent_action_provider=lambda _controller: MoveAction("opponent", "tackle"),
    )
    return mode


def _drain_presentation(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()


def test_wild_companion_reinforcement_menu_includes_ball() -> None:
    mode = _start_companion_battle(_window())
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)
    labels = [label for _, label in overlay._current_actions()]
    assert "Ball" in labels
    assert "Praise" in labels


def test_trainer_companion_reinforcement_menu_omits_ball() -> None:
    bench = MonsterInstance(PLAYER_SPECIES, level=5, current_hp=20, known_moves=("tackle",))
    mode = _start_companion_battle(
        _window(),
        return_context={"source": "trainer_debug_key", "battle_type": "trainer"},
        opponent_party=[
            MonsterInstance(OPPONENT_SPECIES, level=6, current_hp=20, known_moves=("tackle",)),
            bench,
        ],
    )
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)
    labels = [label for _, label in overlay._current_actions()]
    assert "Ball" not in labels


def test_bag_back_returns_to_companion_reinforcement_menu() -> None:
    mode = _start_companion_battle(_window())
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)
    overlay._activate_action("menu:bag")
    assert overlay.menu_state == "bag"
    overlay._activate_action("back")
    assert overlay.menu_state == "root"
    assert mode.companion_awaiting_reinforcement is True
    labels = [label for _, label in overlay._current_actions()]
    assert "Praise" in labels


_COMPANION_RNG_PAD = (0.5, 0.5, 0.5, 0.5)


def test_failed_companion_capture_continues_battle() -> None:
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: ["sproutling_0001"],
        MONSTER_INSTANCES_KEY: {
            "sproutling_0001": serialize_monster_instance(
                MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",)),
            ),
        },
        POCKET_BALL_COUNT_KEY: 2,
    }
    window = _window(values=values)
    mode = _start_companion_battle(
        window,
        opponent_species=HARD_TO_CATCH,
        rng=_Rng(*_COMPANION_RNG_PAD, 0.99),
    )
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)
    overlay._activate_action("menu:bag")
    overlay._activate_action("capture:pocket_ball")
    assert mode.active is True
    assert values[POCKET_BALL_COUNT_KEY] == 1
    assert overlay.menu_state == "presenting"
    assert any("broke free" in step.line for step in overlay.presentation_queue)
    assert len(values[MONSTER_PARTY_KEY]) == 1


def test_companion_capture_success_persists_through_snapshot(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.game_state_controller import GameStateController

    monkeypatch.chdir(tmp_path)
    (tmp_path / "saves").mkdir(parents=True, exist_ok=True)
    save_path = tmp_path / "saves" / "quick.json"

    player_row = serialize_monster_instance(
        MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",)),
    )
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: ["sproutling_0001"],
        MONSTER_INSTANCES_KEY: {"sproutling_0001": dict(player_row)},
        POCKET_BALL_COUNT_KEY: 3,
    }
    window = _window(values=values)
    window.game_state_controller = GameStateController(window)
    window.game_state_controller.state.values = values
    window.engine_config = types.SimpleNamespace(world_file="packs/core_regions/worlds/main.json")
    window.scene_controller = types.SimpleNamespace(current_scene_path="packs/core_regions/scenes/start.json")

    mode = _start_companion_battle(window, rng=_Rng(*_COMPANION_RNG_PAD, 0.0))
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)
    overlay._activate_action("menu:bag")
    overlay._activate_action("capture:pocket_ball")
    _drain_presentation(mode)

    assert mode.active is False
    party = values[MONSTER_PARTY_KEY]
    assert party[0] == "sproutling_0001"
    assert len(party) == 2
    caught_id = str(party[1])
    assert values[MONSTER_INSTANCES_KEY][caught_id]["species_id"] == "shelltide"
    assert values[POCKET_BALL_COUNT_KEY] == 2

    assert savegame.save_quick_snapshot(window, path=save_path) is True

    reload_window = _window()
    reload_window.game_state_controller = GameStateController(reload_window)
    reload_window.engine_config = window.engine_config
    reload_window.scene_controller = window.scene_controller
    assert savegame.load_quick_snapshot(reload_window, path=save_path) is True
    restored = reload_window.game_state_controller.state.values
    assert len(restored[MONSTER_PARTY_KEY]) == 2
    assert restored[POCKET_BALL_COUNT_KEY] == 2
    assert restored[MONSTER_INSTANCES_KEY][caught_id]["species_id"] == "shelltide"


def test_companion_capture_does_not_clobber_active_party_member() -> None:
    """MON-1b-fix regression: caught monster appends without overwriting sproutling row."""
    player_row = serialize_monster_instance(
        MonsterInstance(PLAYER_SPECIES, level=8, current_hp=18, known_moves=("tackle",)),
    )
    values: dict[str, Any] = {
        MONSTER_PARTY_KEY: ["sproutling_0001"],
        MONSTER_INSTANCES_KEY: {"sproutling_0001": dict(player_row)},
        POCKET_BALL_COUNT_KEY: 3,
    }
    window = _window(values=values)
    mode = _start_companion_battle(window, rng=_Rng(*_COMPANION_RNG_PAD, 0.0))
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)
    overlay._activate_action("menu:bag")
    overlay._activate_action("capture:pocket_ball")
    _drain_presentation(mode)

    assert values[MONSTER_PARTY_KEY][0] == "sproutling_0001"
    assert values[MONSTER_INSTANCES_KEY]["sproutling_0001"]["species_id"] == "sproutling"
    assert len(values[MONSTER_PARTY_KEY]) == 2
