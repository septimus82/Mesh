from __future__ import annotations

import random
import types
from unittest.mock import MagicMock

import pytest

from engine.behaviours import load_builtin_behaviours
from engine.behaviours.monster_encounter_zone import MonsterEncounterZoneBehaviour
from engine.behaviours.registry import BEHAVIOUR_REGISTRY
from engine.game_state_controller import GameStateController
from engine.monster.battle_model import BattleStats, Move, Species
from engine.monster.collection import companion_mind_to_dict, ensure_monster_collection, serialize_monster_instance
from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament
from engine.monster.data_load import MonsterCatalog

pytestmark = pytest.mark.fast


TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
EMBER = Move(id="ember", type="fire", power=40, accuracy=100, pp=25)
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
PLAYER = Species(
    id="starter",
    base_stats=BattleStats(hp=35, atk=12, defense=10, spd=10),
    types=("normal",),
    learnset=("tackle",),
)


def _catalog() -> MonsterCatalog:
    return MonsterCatalog(
        species={species.id: species for species in (SPROUT, SHELL, PLAYER)},
        moves={move.id: move for move in (TACKLE, EMBER)},
        type_chart={"fire": {"grass": 2.0}},
        known_types=frozenset({"normal", "fire", "grass", "water"}),
    )


def _entity() -> types.SimpleNamespace:
    return types.SimpleNamespace(center_x=10.0, center_y=20.0, mesh_name="grass_patch_a", mesh_id="zone-1")


def _player() -> types.SimpleNamespace:
    return types.SimpleNamespace(center_x=12.0, center_y=21.0, mesh_name="Player")


def _window() -> types.SimpleNamespace:
    player = _player()
    window = types.SimpleNamespace()
    window.monster_catalog = _catalog()
    window.monster_battle_mode = types.SimpleNamespace(active=False)
    window.scene_controller = types.SimpleNamespace(current_scene_path="scenes/field.json")
    window.start_monster_battle = MagicMock()
    window.find_sprite_by_name = MagicMock(side_effect=lambda name: player if name == "Player" else None)
    window.get_flag = MagicMock(return_value=True)
    return window


def _config(**overrides):
    base = {
        "trigger_radius": 16.0,
        "trigger_target": "Player",
        "encounter_id": "field_grass_01",
        "player_species_id": "starter",
        "player_level": 7,
        "cooldown_seconds": 2.0,
        "encounter_table": [
            {"species_id": "sproutling", "level": 4, "weight": 1},
            {"species_id": "shelltide", "level": 5, "weight": 1},
        ],
    }
    base.update(overrides)
    return base


def test_monster_encounter_zone_registered_as_builtin() -> None:
    load_builtin_behaviours(force=True)
    assert BEHAVIOUR_REGISTRY["MonsterEncounterZone"].__name__ == MonsterEncounterZoneBehaviour.__name__


def test_entering_eligible_zone_starts_battle_with_expected_monster_and_return_context() -> None:
    window = _window()
    behaviour = MonsterEncounterZoneBehaviour(_entity(), window, **_config(rng=random.Random(1)))

    behaviour.update(0.016)

    window.start_monster_battle.assert_called_once()
    kwargs = window.start_monster_battle.call_args.kwargs
    assert kwargs["opponent_monster"].species.id == "sproutling"
    assert kwargs["opponent_monster"].level == 4
    assert kwargs["player_monster"].species.id == "starter"
    assert kwargs["player_monster"].level == 7
    assert kwargs["moves"] == window.monster_catalog.moves
    assert kwargs["type_chart"] == window.monster_catalog.type_chart
    assert kwargs["return_context"] == {
        "scene_path": "scenes/field.json",
        "zone_id": "grass_patch_a",
        "encounter_id": "field_grass_01",
        "species_id": "sproutling",
        "level": 4,
    }
    assert kwargs.get("companion_mode") is not True
    assert "companion_mind" not in kwargs


def test_disabled_zone_or_cooldown_does_not_start_battle() -> None:
    disabled_window = _window()
    disabled = MonsterEncounterZoneBehaviour(_entity(), disabled_window, **_config(enabled=False))
    disabled.update(0.016)
    disabled_window.start_monster_battle.assert_not_called()

    cooldown_window = _window()
    cooldown = MonsterEncounterZoneBehaviour(_entity(), cooldown_window, **_config(rng=random.Random(1)))
    cooldown.update(0.016)
    cooldown.update(0.016)
    assert cooldown_window.start_monster_battle.call_count == 1


def test_enabled_flag_must_be_true() -> None:
    window = _window()
    window.get_flag.return_value = False
    behaviour = MonsterEncounterZoneBehaviour(
        _entity(),
        window,
        **_config(enabled_flag="monster.encounters.enabled", rng=random.Random(1)),
    )

    behaviour.update(0.016)

    window.start_monster_battle.assert_not_called()
    window.get_flag.assert_called_once_with("monster.encounters.enabled", False)


def test_encounter_table_roll_is_deterministic_under_fixed_seed() -> None:
    first_window = _window()
    second_window = _window()
    first = MonsterEncounterZoneBehaviour(
        _entity(),
        first_window,
        **_config(encounter_table=[{"species_id": "sproutling", "min_level": 2, "max_level": 6, "weight": 1}], rng=random.Random(42)),
    )
    second = MonsterEncounterZoneBehaviour(
        _entity(),
        second_window,
        **_config(encounter_table=[{"species_id": "sproutling", "min_level": 2, "max_level": 6, "weight": 1}], rng=random.Random(42)),
    )

    first.update(0.016)
    second.update(0.016)

    first_monster = first_window.start_monster_battle.call_args.kwargs["opponent_monster"]
    second_monster = second_window.start_monster_battle.call_args.kwargs["opponent_monster"]
    assert (first_monster.species.id, first_monster.level) == (second_monster.species.id, second_monster.level)


def test_unknown_species_id_records_validation_error_without_starting_battle() -> None:
    window = _window()
    behaviour = MonsterEncounterZoneBehaviour(
        _entity(),
        window,
        **_config(encounter_table=[{"species_id": "missingno", "level": 3, "weight": 1}], rng=random.Random(1)),
    )

    behaviour.update(0.016)

    window.start_monster_battle.assert_not_called()
    assert "unknown species 'missingno'" in behaviour.last_error


def _companion_window(*, party: list[str] | None = None) -> types.SimpleNamespace:
    window = _window()
    window.game_state_controller = GameStateController(window)
    values = window.game_state_controller.state.values
    if party:
        for instance_id in party:
            values["monster_party"].append(instance_id)
    return window


def _seed_party(values: dict, *, instance_id: str = "sproutling_0001") -> None:
    from engine.monster.battle_model import MonsterInstance

    ensure_monster_collection(values)
    monster = MonsterInstance(SPROUT, level=6, known_moves=SPROUT.learnset)
    mind = CompanionMind(
        temperament=Temperament(aggression=70.0, fear=10.0),
        learned=LearnedWeights(),
        trust=55.0,
        bond=45.0,
    )
    values["monster_instances"][instance_id] = serialize_monster_instance(
        monster,
        companion_mind=companion_mind_to_dict(mind),
    )
    values["monster_party"] = [instance_id]


def test_companion_mode_zone_starts_companion_battle_with_party_mind_and_wild_opponent() -> None:
    window = _companion_window()
    _seed_party(window.game_state_controller.state.values)
    behaviour = MonsterEncounterZoneBehaviour(
        _entity(),
        window,
        **_config(companion_mode=True, rng=random.Random(1)),
    )

    behaviour.update(0.016)

    window.start_monster_battle.assert_called_once()
    kwargs = window.start_monster_battle.call_args.kwargs
    assert kwargs["companion_mode"] is True
    assert kwargs["companion_mind"] is not None
    assert kwargs["player_monster"].species.id == "sproutling"
    assert kwargs["player_party"][0].species.id == "sproutling"
    assert kwargs["player_party_instance_ids"] == ["sproutling_0001"]
    assert kwargs["opponent_monster"].species.id == "sproutling"
    assert kwargs["opponent_monster"].level == 4
    assert kwargs["return_context"]["companion_mode"] is True
    assert kwargs["return_context"]["player_instance_id"] == "sproutling_0001"


def test_companion_mode_without_caught_monster_falls_back_without_crashing() -> None:
    window = _companion_window()
    behaviour = MonsterEncounterZoneBehaviour(
        _entity(),
        window,
        **_config(companion_mode=True, rng=random.Random(1)),
    )

    behaviour.update(0.016)

    window.start_monster_battle.assert_called_once()
    kwargs = window.start_monster_battle.call_args.kwargs
    assert kwargs["companion_mode"] is True
    assert kwargs["companion_mind"] is not None
    assert kwargs["player_monster"].species.id == "sproutling"
    assert kwargs["player_party_instance_ids"][0]


def test_companion_mode_preserves_deterministic_encounter_roll() -> None:
    first_window = _window()
    second_window = _window()
    first = MonsterEncounterZoneBehaviour(
        _entity(),
        first_window,
        **_config(
            companion_mode=True,
            encounter_table=[{"species_id": "sproutling", "min_level": 2, "max_level": 6, "weight": 1}],
            rng=random.Random(42),
        ),
    )
    second = MonsterEncounterZoneBehaviour(
        _entity(),
        second_window,
        **_config(
            companion_mode=True,
            encounter_table=[{"species_id": "sproutling", "min_level": 2, "max_level": 6, "weight": 1}],
            rng=random.Random(42),
        ),
    )

    first.update(0.016)
    second.update(0.016)

    first_monster = first_window.start_monster_battle.call_args.kwargs["opponent_monster"]
    second_monster = second_window.start_monster_battle.call_args.kwargs["opponent_monster"]
    assert (first_monster.species.id, first_monster.level) == (second_monster.species.id, second_monster.level)
    assert first_window.start_monster_battle.call_args.kwargs["companion_mode"] is True
