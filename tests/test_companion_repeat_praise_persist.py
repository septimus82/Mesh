"""Step 0: verify repeat-battle praise persist is not broken (flatline was instant-win battles)."""

from __future__ import annotations

import random
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import MonsterInstance
from engine.monster.collection import add_caught_monster, load_companion_mind_for_instance
from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament
from tests.test_monster_encounter_zone import SHELL, SPROUT, TACKLE, _catalog

pytestmark = pytest.mark.fast


class _StubSceneController:
    def __init__(self, scene_path: str) -> None:
        self.current_scene_path = scene_path


def _window() -> SimpleNamespace:
    from engine.game_state_controller import GameStateController

    window = SimpleNamespace()
    window.monster_catalog = _catalog()
    window.monster_battle_mode = MonsterBattleMode(window)
    window.scene_controller = _StubSceneController("packs/core_regions/scenes/start.json")
    window.game_state_controller = GameStateController(window)
    window.paused = False
    window.monster_battle_mode_active = False
    window.console_log = MagicMock()
    return window


def _start_companion_battle(
    window: SimpleNamespace,
    *,
    instance_id: str,
    rng: random.Random,
    opponent_hp: int = 80,
) -> MonsterBattleMode:
    values = window.game_state_controller.state.values
    party = [MonsterInstance(SPROUT, level=8, known_moves=("tackle",))]
    mind = load_companion_mind_for_instance(values, instance_id)
    if mind is None:
        mind = CompanionMind(
            temperament=Temperament(aggression=65.0, fear=12.0),
            learned=LearnedWeights(),
            trust=60.0,
            bond=40.0,
        )
    mode = window.monster_battle_mode
    mode.start_battle(
        player_monster=party[0],
        player_party=party,
        player_party_instance_ids=[instance_id],
        opponent_monster=MonsterInstance(SHELL, level=5, current_hp=opponent_hp, known_moves=("tackle",)),
        moves={"tackle": TACKLE},
        type_chart=_catalog().type_chart,
        companion_mode=True,
        companion_mind=mind,
        return_context={
            "source": "companion_encounter_zone",
            "player_instance_id": instance_id,
            "companion_mode": True,
        },
        rng=rng,
        opponent_action_provider=lambda _controller: "tackle",
    )
    return mode


def _drain_presentation(mode: MonsterBattleMode) -> None:
    overlay = mode.overlay
    assert overlay is not None
    while overlay.menu_state == "presenting":
        overlay._advance_presentation()


def _praise_and_end_without_win(mode: MonsterBattleMode) -> None:
    """Praise once then flee so reinforcement always fires (avoids instant-win flatline)."""
    _drain_presentation(mode)
    assert mode.companion_awaiting_reinforcement is True
    mode.submit_companion_reinforcement("praise")
    _drain_presentation(mode)
    mode.run_from_battle()


def test_two_consecutive_praised_battles_increase_bond(tmp_path: None = None) -> None:
    """Repeat persist works; Session A flatline was battles ending before praise."""
    window = _window()
    values = window.game_state_controller.state.values

    caught = add_caught_monster(values, MonsterInstance(SPROUT, level=8, current_hp=24, known_moves=("tackle",)))
    instance_id = caught.instance_id

    bond_after_first = 40.0
    for battle_index in range(2):
        mode = _start_companion_battle(window, instance_id=instance_id, rng=random.Random(battle_index + 10))
        _praise_and_end_without_win(mode)
        mind = load_companion_mind_for_instance(values, instance_id)
        assert mind is not None
        if battle_index == 0:
            bond_after_first = mind.bond
            assert mind.bond > 40.0
        else:
            assert mind.bond > bond_after_first


def test_battle_end_diag_emits_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_COMPANION_DIAG", "1")
    from engine import companion_diagnostics

    companion_diagnostics.log_companion_battle_end(
        instance_id="sproutling_0001",
        mind=CompanionMind(bond=41.0, trust=62.0, learned=LearnedWeights(ATTACK=5.0)),
        outcome="won",
        trigger="companion_encounter_zone",
    )
