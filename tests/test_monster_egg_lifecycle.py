"""Tests for monster egg lifecycle and breeding debug integration."""

from __future__ import annotations

import random
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.game import GameWindow
from engine.game_state_controller import GameStateController
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.breeding import BreedingParent, breed_offspring
from engine.monster.collection import (
    MONSTER_PARTY_KEY,
    add_caught_monster,
    companion_mind_to_dict,
    ensure_monster_collection,
    load_companion_mind_for_instance,
)
from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament
from engine.monster.egg_lifecycle import (
    DEFAULT_EGG_HATCH_STEPS,
    MONSTER_EGGS_KEY,
    STEPS_REMAINING_KEY,
    create_breeding_egg,
    tick_monster_eggs,
)
from engine.monster.overworld_egg_steps import OVERWORLD_PIXELS_PER_EGG_STEP
from engine.save_manager import SaveManager
from tests._typing import as_any

pytestmark = pytest.mark.fast

TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
SPROUT = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=10, defense=10, spd=8),
    types=("grass",),
    learnset=("tackle",),
)
SHELL = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)
SPECIES = {SPROUT.id: SPROUT, SHELL.id: SHELL}


def _mind(aggression: float, fear: float, *, traits: tuple[str, ...] = ()) -> CompanionMind:
    return CompanionMind(
        temperament=Temperament(aggression=aggression, fear=fear),
        learned=LearnedWeights(ATTACK=20.0, DEFEND=10.0, HESITATE=5.0),
        trust=70.0,
        bond=55.0,
        traits=traits,
    )


def _window_for_save() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.engine_config = types.SimpleNamespace(debug_mode=True)
    window.console_log = MagicMock()
    window.game_state_controller = GameStateController(window)
    window.monster_catalog = types.SimpleNamespace(species=SPECIES)
    window.scene_controller = types.SimpleNamespace(
        current_scene_path="scenes/test_scene.json",
        build_scene_snapshot=MagicMock(return_value={"entities": [], "settings": {"camera": {}}}),
    )
    window.camera_controller = types.SimpleNamespace(
        zoom_state=types.SimpleNamespace(current=1.0, target=1.0, speed=0.1, min_zoom=0.5, max_zoom=2.0),
    )
    window.request_scene_change = MagicMock()
    return window


def _window() -> types.SimpleNamespace:
    return _window_for_save()


def _seed_two_party_monsters(values: dict) -> tuple[str, str]:
    ensure_monster_collection(values)
    first = add_caught_monster(values, MonsterInstance(SPROUT, level=6, known_moves=SPROUT.learnset))
    second = add_caught_monster(values, MonsterInstance(SHELL, level=5, known_moves=SHELL.learnset))
    values["monster_instances"][first.instance_id]["companion_mind"] = companion_mind_to_dict(
        _mind(60.0, 20.0, traits=("brave",))
    )
    values["monster_instances"][second.instance_id]["companion_mind"] = companion_mind_to_dict(
        _mind(30.0, 40.0, traits=("timid",))
    )
    return first.instance_id, second.instance_id


def test_egg_hatches_after_n_steps_into_party_with_inherited_mind() -> None:
    values: dict = {}
    offspring, mind = breed_offspring(
        BreedingParent(MonsterInstance(SPROUT, level=1, known_moves=SPROUT.learnset), _mind(60.0, 20.0)),
        BreedingParent(MonsterInstance(SHELL, level=1, known_moves=SHELL.learnset), _mind(30.0, 40.0)),
        random.Random(5),
    )
    create_breeding_egg(values, offspring=offspring, mind=mind, hatch_steps=3)

    assert tick_monster_eggs(values, species_by_id=SPECIES, steps=1) == []
    assert tick_monster_eggs(values, species_by_id=SPECIES, steps=1) == []
    events = tick_monster_eggs(values, species_by_id=SPECIES, steps=1)

    assert len(events) == 1
    assert events[0].species_id in SPECIES
    assert values[MONSTER_EGGS_KEY] == []
    assert len(values[MONSTER_PARTY_KEY]) == 1
    restored = load_companion_mind_for_instance(values, events[0].instance_id)
    assert restored is not None
    assert companion_mind_to_dict(restored) == companion_mind_to_dict(mind)


def test_hatched_offspring_persists_through_save_roundtrip(tmp_path: Path) -> None:
    values: dict = {}
    offspring, mind = breed_offspring(
        BreedingParent(MonsterInstance(SPROUT, level=1, known_moves=SPROUT.learnset), _mind(55.0, 25.0)),
        BreedingParent(MonsterInstance(SHELL, level=1, known_moves=SHELL.learnset), _mind(35.0, 35.0)),
        random.Random(11),
    )
    create_breeding_egg(values, offspring=offspring, mind=mind, hatch_steps=1)

    source_window = _window_for_save()
    source_window.game_state_controller.state.values = values
    tick_monster_eggs(source_window.game_state_controller.state.values, species_by_id=SPECIES)

    save_path = tmp_path / "breeding_save.json"
    manager = SaveManager(as_any(source_window))
    manager.save_game(str(save_path))

    fresh = _window_for_save()
    fresh.game_state_controller.state.values = {}
    SaveManager(as_any(fresh)).load_game(str(save_path))
    party_ids = fresh.game_state_controller.state.values.get(MONSTER_PARTY_KEY, [])
    assert party_ids
    restored = load_companion_mind_for_instance(fresh.game_state_controller.state.values, party_ids[0])
    assert restored is not None
    assert restored.trust == pytest.approx(mind.trust)
    assert restored.temperament.aggression == pytest.approx(mind.temperament.aggression, abs=0.01)


def test_debug_breed_first_party_pair_creates_egg() -> None:
    window = _window()
    values = window.game_state_controller.state.values
    _seed_two_party_monsters(values)

    assert GameWindow.debug_breed_first_party_pair(as_any(window)) is True

    eggs = values.get(MONSTER_EGGS_KEY, [])
    assert len(eggs) == 1
    assert eggs[0]["steps_remaining"] == DEFAULT_EGG_HATCH_STEPS
    assert isinstance(eggs[0]["offspring"], dict)
    window.console_log.assert_called()


def test_debug_breed_requires_two_party_monsters_without_crashing() -> None:
    window = _window()
    values = window.game_state_controller.state.values
    ensure_monster_collection(values)
    add_caught_monster(values, MonsterInstance(SPROUT, level=4, known_moves=SPROUT.learnset))

    assert GameWindow.debug_breed_first_party_pair(as_any(window)) is False
    assert values.get(MONSTER_EGGS_KEY, []) == []


def test_game_state_controller_emits_hatch_notice(tmp_path: Path) -> None:  # noqa: ARG001
    window = _window()
    values = window.game_state_controller.state.values
    offspring, mind = breed_offspring(
        BreedingParent(MonsterInstance(SPROUT, level=1, known_moves=SPROUT.learnset), _mind(50.0, 10.0)),
        BreedingParent(MonsterInstance(SHELL, level=1, known_moves=SHELL.learnset), _mind(40.0, 20.0)),
        random.Random(2),
    )
    create_breeding_egg(values, offspring=offspring, mind=mind, hatch_steps=1)

    window.game_state_controller.record_overworld_walk_distance(OVERWORLD_PIXELS_PER_EGG_STEP)

    window.console_log.assert_called()
    assert "emerges" in str(window.console_log.call_args.args[0]).lower()


def test_pending_egg_survives_save_roundtrip_mid_incubation(tmp_path: Path) -> None:
    values: dict = {}
    offspring, mind = breed_offspring(
        BreedingParent(MonsterInstance(SPROUT, level=1, known_moves=SPROUT.learnset), _mind(55.0, 25.0)),
        BreedingParent(MonsterInstance(SHELL, level=1, known_moves=SHELL.learnset), _mind(35.0, 35.0)),
        random.Random(11),
    )
    create_breeding_egg(values, offspring=offspring, mind=mind, hatch_steps=120)

    source_window = _window_for_save()
    source_window.game_state_controller.state.values = values

    save_path = tmp_path / "egg_mid_incubation.json"
    manager = SaveManager(as_any(source_window))
    manager.save_game(str(save_path))

    fresh = _window_for_save()
    fresh.game_state_controller.state.values = {}
    SaveManager(as_any(fresh)).load_game(str(save_path))
    loaded_values = fresh.game_state_controller.state.values
    eggs = loaded_values.get(MONSTER_EGGS_KEY, [])
    assert len(eggs) == 1
    assert eggs[0][STEPS_REMAINING_KEY] == 120
