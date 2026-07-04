from __future__ import annotations

import random
import types
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from engine.game_state_controller import GameStateController
from engine.monster.battle_controller import BattleResult
from engine.monster.battle_mode import MONSTER_BATTLE_RESULT_KEY, MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.collection import (
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    add_caught_monster,
    load_companion_mind_for_instance,
)
from engine.monster.companion_mind import (
    ATTACK,
    FLEE,
    CompanionMind,
    DecisionContext,
    DecisionResult,
    LearnedWeights,
    Temperament,
    companion_mind_from_dict,
    companion_mind_to_dict,
    score_behaviors,
)
from engine.save_manager import SaveManager
from engine.ui_controller import UIController
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
    window.game_over = False
    window.show_debug = False
    window.monster_battle_mode_active = False
    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)
    window.game_state_controller = GameStateController(as_any(window))
    window.ui_controller = UIController(as_any(window))
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    return window


def _window_for_save() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.game_state_controller = GameStateController(window)
    window.scene_controller = types.SimpleNamespace(
        current_scene_path="scenes/test_scene.json",
        build_scene_snapshot=MagicMock(return_value={"entities": [], "settings": {"camera": {}}}),
    )
    window.camera_controller = types.SimpleNamespace(
        zoom_state=types.SimpleNamespace(current=1.0, target=1.0, speed=0.1, min_zoom=0.5, max_zoom=2.0),
    )
    window.request_scene_change = MagicMock()
    return window


def _drain_presentation(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()


def _start_companion_battle(
    window: types.SimpleNamespace,
    *,
    instance_id: str,
    mind: CompanionMind | None = None,
    player_hp: int | None = None,
    rng: random.Random | None = None,
) -> MonsterBattleMode:
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    player = MonsterInstance(
        PLAYER_SPECIES,
        level=10,
        current_hp=player_hp if player_hp is not None else 30,
        known_moves=("tackle",),
    )
    mode.start_battle(
        player_monster=player,
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, current_hp=40, known_moves=("tackle",)),
        moves={TACKLE.id: TACKLE},
        type_chart={"grass": {"water": 2.0}},
        player_party=[player],
        player_party_instance_ids=[instance_id],
        companion_mode=True,
        companion_mind=mind
        or CompanionMind(temperament=Temperament(aggression=55.0, fear=10.0), learned=LearnedWeights(), trust=50.0),
        rng=rng or random.Random(0),
        opponent_action_provider=lambda _controller: "tackle",
    )
    return mode


def test_companion_mind_dict_round_trip_is_exact() -> None:
    mind = CompanionMind(
        temperament=Temperament(aggression=65.5, fear=18.25),
        learned=LearnedWeights(ATTACK=4.5, DEFEND=-2.0, HESITATE=1.25),
        trust=72.5,
        bond=11.0,
        mood=-18.0,
        traits=("timid", "loyal"),
        last_behavior=ATTACK,
    )

    restored = companion_mind_from_dict(companion_mind_to_dict(mind))

    assert restored == mind


def test_flee_not_available_for_low_hp_high_trust_companion() -> None:
    mind = CompanionMind(
        temperament=Temperament(aggression=10.0, fear=80.0),
        learned=LearnedWeights(),
        trust=90.0,
        bond=85.0,
    )
    ctx = DecisionContext(hp_fraction=0.2)

    scores = score_behaviors(mind, ctx)

    assert FLEE not in scores


def test_flee_available_for_low_hp_neglected_companion() -> None:
    mind = CompanionMind(
        temperament=Temperament(aggression=10.0, fear=70.0),
        learned=LearnedWeights(),
        trust=10.0,
        bond=5.0,
    )
    ctx = DecisionContext(hp_fraction=0.2)

    scores = score_behaviors(mind, ctx)

    assert FLEE in scores
    assert scores[FLEE] > 0.0


def test_companion_mind_trained_in_battle_survives_save_manager_roundtrip(tmp_path: Path) -> None:
    window = _window_for_save()
    values = window.game_state_controller.state.values
    monster = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=24, known_moves=("tackle",))
    caught = add_caught_monster(values, monster)
    instance_id = caught.instance_id

    battle_window = _window()
    battle_window.game_state_controller = window.game_state_controller
    mode = _start_companion_battle(battle_window, instance_id=instance_id, rng=random.Random(3))
    _drain_presentation(mode)
    trust_before = mode.companion_mind.trust
    mode.submit_companion_reinforcement("praise")
    _drain_presentation(mode)
    assert mode.companion_mind is not None
    trained_trust = mode.companion_mind.trust
    trained_bond = mode.companion_mind.bond
    assert trained_trust > trust_before

    mode.end_battle(
        BattleResult(cast(Any, "won"), winning_side="player", losing_side="opponent", turns=mode.controller.turn_number),
    )

    reloaded_before_save = load_companion_mind_for_instance(values, instance_id)
    assert reloaded_before_save is not None
    assert reloaded_before_save.trust == pytest.approx(trained_trust)
    assert reloaded_before_save.bond == pytest.approx(trained_bond)

    manager = SaveManager(window, save_dir=str(tmp_path))
    assert manager.save_game("slot1") is True

    fresh = _window_for_save()
    fresh_manager = SaveManager(fresh, save_dir=str(tmp_path))
    assert fresh_manager.load_game("slot1") is True
    restored = load_companion_mind_for_instance(fresh.game_state_controller.state.values, instance_id)
    assert restored is not None
    assert restored.trust > trust_before
    assert restored.bond > 0.0


def test_lone_companion_flee_ends_battle_with_failed_bond_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window()
    values = window.game_state_controller.state.values
    monster = MonsterInstance(PLAYER_SPECIES, level=8, current_hp=4, known_moves=("tackle",))
    caught = add_caught_monster(values, monster)
    neglected = CompanionMind(
        temperament=Temperament(aggression=10.0, fear=80.0),
        learned=LearnedWeights(),
        trust=5.0,
        bond=0.0,
    )

    def _force_flee(mind: CompanionMind, ctx: DecisionContext, rng: object, *, registry: object = ()) -> tuple[CompanionMind, DecisionResult]:
        updated = replace(mind, last_behavior=FLEE)
        return updated, DecisionResult(behavior_id=FLEE, scores={FLEE: 999.0})

    monkeypatch.setattr("engine.monster.battle_mode.decide", _force_flee)

    mode = _start_companion_battle(window, instance_id=caught.instance_id, mind=neglected, player_hp=4)
    overlay = mode.overlay
    assert overlay is not None
    _drain_presentation(mode)

    assert overlay.menu_state == "ended"
    result_payload = values[MONSTER_BATTLE_RESULT_KEY]
    assert result_payload["outcome"] == "fled"
    assert caught.instance_id not in values[MONSTER_PARTY_KEY]
    assert caught.instance_id not in values[MONSTER_INSTANCES_KEY]
    assert overlay.log_line == "It abandoned you."
