"""Companion abandonment: flee removes party member and survives snapshot reload."""

from __future__ import annotations

import random
import types
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine import savegame
from engine.behaviours.monster_encounter_zone import MonsterEncounterZoneBehaviour
from engine.game_state_controller import GameStateController
from engine.monster.battle_mode import MONSTER_BATTLE_RESULT_KEY, MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.collection import (
    MONSTER_INSTANCES_KEY,
    MONSTER_PARTY_KEY,
    add_caught_monster,
    default_companion_mind_for_instance,
    mark_companion_starter_granted,
    mark_companion_starter_instance,
)
from engine.monster.companion_mind import (
    FLEE,
    FLEE_RELATIONSHIP_THRESHOLD,
    CompanionMind,
    DecisionContext,
    DecisionResult,
    LearnedWeights,
    Temperament,
    bonded_starter_companion_mind,
    default_caught_companion_mind,
    scold,
    score_behaviors,
)
from engine.ui_controller import UIController
from tests._typing import as_any
from tests.test_monster_encounter_zone import _catalog, _companion_window, _config, _entity

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
    party: list[MonsterInstance] | None = None,
    party_ids: list[str] | None = None,
    rng: random.Random | None = None,
) -> MonsterBattleMode:
    player = MonsterInstance(
        PLAYER_SPECIES,
        level=10,
        current_hp=player_hp if player_hp is not None else 30,
        known_moves=("tackle",),
    )
    party = party or [player]
    party_ids = party_ids or [instance_id]
    mode = MonsterBattleMode(as_any(window))
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=player,
        opponent_monster=MonsterInstance(OPPONENT_SPECIES, level=10, current_hp=40, known_moves=("tackle",)),
        moves={TACKLE.id: TACKLE},
        type_chart={"grass": {"water": 2.0}},
        player_party=party,
        player_party_instance_ids=party_ids,
        companion_mode=True,
        companion_mind=mind
        or CompanionMind(temperament=Temperament(aggression=55.0, fear=10.0), learned=LearnedWeights(), trust=50.0),
        rng=rng or random.Random(0),
        opponent_action_provider=lambda _controller: "tackle",
    )
    return mode


def _force_flee(monkeypatch: pytest.MonkeyPatch) -> None:
    def _decide(mind: CompanionMind, ctx: DecisionContext, rng: object, *, registry: object = ()) -> tuple[CompanionMind, DecisionResult]:
        updated = replace(mind, last_behavior=FLEE)
        return updated, DecisionResult(behavior_id=FLEE, scores={FLEE: 999.0})

    monkeypatch.setattr("engine.monster.battle_mode.decide", _decide)


def test_flee_removes_instance_from_party_and_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window()
    values = window.game_state_controller.state.values
    caught = add_caught_monster(values, MonsterInstance(PLAYER_SPECIES, level=8, current_hp=4, known_moves=("tackle",)))
    mark_companion_starter_instance(values, caught.instance_id)
    _force_flee(monkeypatch)

    mode = _start_companion_battle(
        window,
        instance_id=caught.instance_id,
        mind=CompanionMind(temperament=Temperament(aggression=10.0, fear=80.0), learned=LearnedWeights(), trust=5.0, bond=0.0),
        player_hp=4,
    )
    _drain_presentation(mode)

    assert caught.instance_id not in values[MONSTER_PARTY_KEY]
    assert caught.instance_id not in values[MONSTER_INSTANCES_KEY]
    assert values[MONSTER_BATTLE_RESULT_KEY]["outcome"] == "fled"


def test_flee_removal_survives_quick_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "saves").mkdir(parents=True, exist_ok=True)
    save_path = tmp_path / "saves" / "quick.json"

    window = _window()
    window.engine_config = types.SimpleNamespace(world_file="packs/core_regions/worlds/main.json")
    window.scene_controller = types.SimpleNamespace(current_scene_path="packs/core_regions/scenes/start.json")
    values = window.game_state_controller.state.values
    caught = add_caught_monster(values, MonsterInstance(PLAYER_SPECIES, level=8, current_hp=4, known_moves=("tackle",)))
    mark_companion_starter_instance(values, caught.instance_id)
    mark_companion_starter_granted(values)
    fled_id = caught.instance_id
    _force_flee(monkeypatch)

    mode = _start_companion_battle(
        window,
        instance_id=fled_id,
        mind=CompanionMind(temperament=Temperament(aggression=10.0, fear=80.0), learned=LearnedWeights(), trust=5.0, bond=0.0),
        player_hp=4,
    )
    _drain_presentation(mode)
    assert fled_id not in values[MONSTER_PARTY_KEY]
    assert savegame.save_quick_snapshot(window, path=save_path) is True

    reload_window = _window()
    reload_window.engine_config = window.engine_config
    reload_window.scene_controller = window.scene_controller
    assert savegame.load_quick_snapshot(reload_window, path=save_path) is True
    restored = reload_window.game_state_controller.state.values
    assert fled_id not in restored.get(MONSTER_PARTY_KEY, [])
    assert fled_id not in restored.get(MONSTER_INSTANCES_KEY, {})


def test_zone_after_abandonment_uses_bench_companion() -> None:
    window = _companion_window()
    values = window.game_state_controller.state.values
    mark_companion_starter_granted(values)
    shell = add_caught_monster(
        values,
        MonsterInstance(_catalog().species["shelltide"], level=5, current_hp=20, known_moves=("tackle",)),
    )
    values[MONSTER_PARTY_KEY] = [shell.instance_id]

    behaviour = MonsterEncounterZoneBehaviour(_entity(), window, **_config(companion_mode=True, rng=random.Random(1)))
    behaviour.update(0.016)

    kwargs = window.start_monster_battle.call_args.kwargs
    assert kwargs["companion_mode"] is True
    assert kwargs["player_party_instance_ids"] == [shell.instance_id]
    mind = kwargs["companion_mind"]
    assert mind.bond == pytest.approx(default_caught_companion_mind().bond)
    assert mind.trust == pytest.approx(default_caught_companion_mind().trust)


def test_zone_with_empty_party_after_abandonment_skips_battle() -> None:
    window = _companion_window()
    values = window.game_state_controller.state.values
    mark_companion_starter_granted(values)
    values[MONSTER_PARTY_KEY] = []
    values[MONSTER_INSTANCES_KEY] = {}

    behaviour = MonsterEncounterZoneBehaviour(_entity(), window, **_config(companion_mode=True, rng=random.Random(1)))
    behaviour.update(0.016)

    window.start_monster_battle.assert_not_called()
    assert "empty" in str(behaviour.last_error).lower()


def test_scold_path_crosses_flee_relationship_threshold() -> None:
    mind = bonded_starter_companion_mind()
    for _ in range(5):
        mind = scold(mind)
    assert (mind.trust + mind.bond) / 2.0 < FLEE_RELATIONSHIP_THRESHOLD
    scores = score_behaviors(mind, DecisionContext(hp_fraction=0.2))
    assert FLEE in scores


def test_bonded_starter_default_differs_from_caught_default() -> None:
    window = _window()
    values = window.game_state_controller.state.values
    starter = add_caught_monster(values, MonsterInstance(PLAYER_SPECIES, level=8, known_moves=("tackle",)))
    caught = add_caught_monster(values, MonsterInstance(OPPONENT_SPECIES, level=5, known_moves=("tackle",)))
    mark_companion_starter_instance(values, starter.instance_id)

    starter_mind = default_companion_mind_for_instance(values, starter.instance_id)
    bench_mind = default_companion_mind_for_instance(values, caught.instance_id)

    assert starter_mind.bond == pytest.approx(40.0)
    assert bench_mind.bond == pytest.approx(15.0)


def test_praised_bonded_starter_still_wont_flee_at_low_hp() -> None:
    mind = bonded_starter_companion_mind()
    for _ in range(3):
        from engine.monster.companion_mind import praise

        mind = praise(mind)
    scores = score_behaviors(mind, DecisionContext(hp_fraction=0.2))
    assert FLEE not in scores
