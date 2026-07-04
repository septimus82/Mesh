from __future__ import annotations

import random
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from engine import savegame
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import MonsterInstance
from engine.monster.collection import (
    add_caught_monster,
    load_companion_mind_for_instance,
)
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


def _start_companion_battle(window: SimpleNamespace, *, instance_id: str, rng: random.Random) -> MonsterBattleMode:
    values = window.game_state_controller.state.values
    party, party_ids = [MonsterInstance(SPROUT, level=8, known_moves=("tackle",))], [instance_id]
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
        player_party_instance_ids=party_ids,
        opponent_monster=MonsterInstance(SHELL, level=5, known_moves=("tackle",)),
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


def _finish_companion_battle(mode: MonsterBattleMode) -> None:
    from engine.monster.battle_controller import BattleResult

    _drain_presentation(mode)
    if mode.companion_awaiting_reinforcement:
        mode.submit_companion_reinforcement("praise")
        _drain_presentation(mode)
    mode.end_battle(
        BattleResult(cast(Any, "won"), winning_side="player", losing_side="opponent", turns=mode.controller.turn_number),
    )


def test_companion_training_survives_quick_snapshot_reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Session A/B regression without GUI: praise in battle -> F5 snapshot -> reload -> saved mind."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "saves").mkdir(parents=True, exist_ok=True)
    save_path = tmp_path / "saves" / "quick.json"

    session_a = _window()
    session_a.engine_config = SimpleNamespace(world_file="packs/core_regions/worlds/main.json")
    values = session_a.game_state_controller.state.values
    caught = add_caught_monster(values, MonsterInstance(SPROUT, level=8, current_hp=24, known_moves=("tackle",)))
    instance_id = caught.instance_id

    bond_before = 40.0
    attack_before = 0.0
    for battle_index in range(3):
        mode = _start_companion_battle(session_a, instance_id=instance_id, rng=random.Random(battle_index + 1))
        _finish_companion_battle(mode)
        mind = load_companion_mind_for_instance(values, instance_id)
        assert mind is not None
        bond_before = mind.bond
        attack_before = float(getattr(mind.learned, "ATTACK", 0.0))

    assert savegame.save_quick_snapshot(session_a, path=save_path) is True

    session_b = _window()
    session_b.engine_config = SimpleNamespace(world_file="packs/core_regions/worlds/main.json")
    assert savegame.load_quick_snapshot(session_b, path=save_path) is True

    reloaded = load_companion_mind_for_instance(session_b.game_state_controller.state.values, instance_id)
    assert reloaded is not None
    assert reloaded.bond == pytest.approx(bond_before)
    assert float(getattr(reloaded.learned, "ATTACK")) == pytest.approx(attack_before)

    mode_b = _start_companion_battle(session_b, instance_id=instance_id, rng=random.Random(99))
    loaded = load_companion_mind_for_instance(session_b.game_state_controller.state.values, instance_id)
    assert loaded is not None
    assert mode_b.companion_mind is not None
    assert mode_b.companion_mind.bond == pytest.approx(bond_before)
    assert float(getattr(mode_b.companion_mind.learned, "ATTACK")) == pytest.approx(attack_before)

    # Fresh run without load still gets bonded baseline when no saved mind exists.
    fresh = _window()
    fresh_values = fresh.game_state_controller.state.values
    fresh_caught = add_caught_monster(fresh_values, MonsterInstance(SPROUT, level=8, known_moves=("tackle",)))
    baseline_mode = _start_companion_battle(fresh, instance_id=fresh_caught.instance_id, rng=random.Random(1))
    assert baseline_mode.companion_mind is not None
    assert baseline_mode.companion_mind.bond == pytest.approx(40.0)
    assert baseline_mode.companion_mind.trust == pytest.approx(60.0)
