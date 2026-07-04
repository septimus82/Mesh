"""Breeding shrine zone behaviour and pure attempt logic."""

from __future__ import annotations

import random
import types
from unittest.mock import MagicMock

import pytest

from engine.behaviours import load_builtin_behaviours
from engine.behaviours.breeding_shrine_zone import BreedingShrineZoneBehaviour
from engine.behaviours.registry import BEHAVIOUR_REGISTRY
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.breeding import BreedingParent, breed_offspring
from engine.monster.breeding_shrine import attempt_breeding_at_shrine, count_pending_eggs
from engine.monster.collection import companion_mind_to_dict, ensure_monster_collection, load_companion_mind_for_instance
from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament, companion_mind_from_dict
from engine.monster.data_load import MonsterCatalog
from engine.monster.egg_lifecycle import MONSTER_EGGS_KEY, STEPS_REMAINING_KEY

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
CATALOG = MonsterCatalog(
    species={SPROUT.id: SPROUT, SHELL.id: SHELL},
    moves={TACKLE.id: TACKLE},
    type_chart={"water": {"grass": 2.0}},
    known_types=frozenset({"grass", "water", "normal"}),
)


def _mind(*, bond: float, aggression: float = 50.0, fear: float = 20.0, traits: tuple[str, ...] = ()) -> CompanionMind:
    return CompanionMind(
        temperament=Temperament(aggression=aggression, fear=fear),
        learned=LearnedWeights(ATTACK=20.0, DEFEND=10.0, HESITATE=5.0),
        trust=60.0,
        bond=bond,
        traits=traits,
    )


def _entity() -> types.SimpleNamespace:
    return types.SimpleNamespace(center_x=700.0, center_y=560.0, mesh_name="Sakura Shrine", mesh_id="shrine-1")


def _player() -> types.SimpleNamespace:
    return types.SimpleNamespace(center_x=710.0, center_y=565.0, mesh_name="Player")


def _window(*, values: dict | None = None) -> types.SimpleNamespace:
    player = _player()
    window = types.SimpleNamespace()
    window.monster_catalog = CATALOG
    window.monster_battle_mode = types.SimpleNamespace(active=False)
    window.console_log = MagicMock()
    window.find_sprite_by_name = MagicMock(side_effect=lambda name: player if name == "Player" else None)
    window.get_flag = MagicMock(return_value=True)
    window.game_state_controller = types.SimpleNamespace(
        state=types.SimpleNamespace(values=values or {}),
        get_flag=MagicMock(return_value=True),
    )
    return window


def _config(**overrides: object) -> dict[str, object]:
    base = {
        "trigger_radius": 80.0,
        "trigger_target": "Player",
        "cooldown_seconds": 0.0,
        "bond_threshold": 50.0,
        "max_eggs": 1,
        "hatch_steps": 200,
        "rng": random.Random(7),
    }
    base.update(overrides)
    return base


def _seed_bonded_party(values: dict, *, first_bond: float, second_bond: float) -> tuple[str, str]:
    ensure_monster_collection(values)
    from engine.monster.collection import add_caught_monster

    first = add_caught_monster(values, MonsterInstance(SPROUT, level=8, known_moves=SPROUT.learnset))
    second = add_caught_monster(values, MonsterInstance(SHELL, level=7, known_moves=SHELL.learnset))
    values["monster_instances"][first.instance_id]["companion_mind"] = companion_mind_to_dict(
        _mind(bond=first_bond, aggression=70.0, traits=("brave",))
    )
    values["monster_instances"][second.instance_id]["companion_mind"] = companion_mind_to_dict(
        _mind(bond=second_bond, aggression=25.0, traits=("timid",))
    )
    return first.instance_id, second.instance_id


def test_behaviour_registry_exposes_breeding_shrine_zone() -> None:
    load_builtin_behaviours(force=True)
    assert BEHAVIOUR_REGISTRY["BreedingShrineZone"].__name__ == BreedingShrineZoneBehaviour.__name__


def test_attempt_breeding_rejects_when_bond_below_threshold() -> None:
    values: dict = {}
    _seed_bonded_party(values, first_bond=49.0, second_bond=55.0)
    result = attempt_breeding_at_shrine(values, catalog=CATALOG, bond_threshold=50.0, rng=random.Random(1))
    assert result.outcome == "not_enough_bonded"
    assert count_pending_eggs(values) == 0


def test_attempt_breeding_rejects_when_max_eggs_reached() -> None:
    values: dict = {MONSTER_EGGS_KEY: [{"egg_id": "egg_0001", STEPS_REMAINING_KEY: 10}]}
    _seed_bonded_party(values, first_bond=60.0, second_bond=55.0)
    result = attempt_breeding_at_shrine(values, catalog=CATALOG, max_eggs=1, rng=random.Random(1))
    assert result.outcome == "egg_waiting"


def test_attempt_breeding_creates_egg_with_inherited_mind_from_parents() -> None:
    values: dict = {}
    parent_a_id, parent_b_id = _seed_bonded_party(values, first_bond=60.0, second_bond=55.0)
    parent_a_mind = load_companion_mind_for_instance(values, parent_a_id)
    parent_b_mind = load_companion_mind_for_instance(values, parent_b_id)
    assert parent_a_mind is not None and parent_b_mind is not None

    expected_offspring, expected_mind = breed_offspring(
        BreedingParent(MonsterInstance(SPROUT, level=8, known_moves=SPROUT.learnset), parent_a_mind),
        BreedingParent(MonsterInstance(SHELL, level=7, known_moves=SHELL.learnset), parent_b_mind),
        random.Random(7),
    )

    result = attempt_breeding_at_shrine(values, catalog=CATALOG, hatch_steps=200, rng=random.Random(7))
    assert result.outcome == "success"
    assert count_pending_eggs(values) == 1
    egg = values[MONSTER_EGGS_KEY][0]
    assert egg[STEPS_REMAINING_KEY] == 200
    assert egg["offspring"]["species_id"] == expected_offspring.species.id
    assert companion_mind_to_dict(companion_mind_from_dict(egg["companion_mind"])) == companion_mind_to_dict(expected_mind)


def test_zone_attempt_logs_success_and_respects_cooldown() -> None:
    values: dict = {}
    _seed_bonded_party(values, first_bond=60.0, second_bond=55.0)
    player = _player()
    window = _window(values=values)
    window.find_sprite_by_name = MagicMock(side_effect=lambda name: player if name == "Player" else None)
    behaviour = BreedingShrineZoneBehaviour(_entity(), window, **_config(cooldown_seconds=5.0))
    behaviour.update(0.016)
    assert behaviour.last_outcome == "success"
    window.console_log.assert_called()
    assert "egg" in str(window.console_log.call_args.args[0]).lower()

    player.center_x = 9999.0
    behaviour.update(0.016)
    player.center_x = 710.0
    behaviour.update(0.016)
    assert behaviour.last_outcome == "cooldown"


def test_zone_rejects_low_bond_with_terms_line() -> None:
    values: dict = {}
    _seed_bonded_party(values, first_bond=15.0, second_bond=20.0)
    window = _window(values=values)
    behaviour = BreedingShrineZoneBehaviour(_entity(), window, **_config())
    behaviour.update(0.016)
    assert behaviour.last_outcome == "not_enough_bonded"
    assert "bond" in str(window.console_log.call_args.args[0]).lower()


def test_hatchling_battle_diag_reflects_inherited_mind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_COMPANION_DIAG", "1")
    captured: list[str] = []

    def _capture(**kwargs: object) -> None:
        captured.append(str(kwargs))

    monkeypatch.setattr("engine.companion_diagnostics.log_companion_battle_start", _capture)

    values: dict = {}
    parent_a_id, parent_b_id = _seed_bonded_party(values, first_bond=60.0, second_bond=55.0)
    result = attempt_breeding_at_shrine(values, catalog=CATALOG, hatch_steps=1, rng=random.Random(7))
    assert result.outcome == "success"

    from engine.game_state_controller import GameStateController
    from engine.monster.battle_mode import MonsterBattleMode
    from engine.monster.collection import load_battle_party_from_values
    from engine.monster.egg_lifecycle import tick_monster_eggs

    events = tick_monster_eggs(values, species_by_id=CATALOG.species, steps=1)
    assert len(events) == 1
    hatchling_id = events[0].instance_id
    hatch_mind = events[0].mind
    assert hatch_mind.temperament.aggression != 50.0 or hatch_mind.learned.ATTACK != 0.0

    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = types.SimpleNamespace(ui_elements=[], register_ui_element=lambda _element: None)
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    window.game_state_controller = GameStateController(window)
    window.game_state_controller.state.values = values
    window.monster_catalog = CATALOG

    party, party_ids = load_battle_party_from_values(
        values,
        CATALOG.species,
        fallback=MonsterInstance(SPROUT, level=1, known_moves=SPROUT.learnset),
    )
    hatch_index = party_ids.index(hatchling_id)
    hatchling = party[hatch_index]
    party = [hatchling, *[monster for index, monster in enumerate(party) if index != hatch_index]]
    party_ids = [hatchling_id, *[instance_id for index, instance_id in enumerate(party_ids) if index != hatch_index]]

    mode = MonsterBattleMode(window)  # type: ignore[arg-type]
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=hatchling,
        player_party=party,
        player_party_instance_ids=party_ids,
        opponent_monster=MonsterInstance(SHELL, level=5, current_hp=20, known_moves=SHELL.learnset),
        moves=CATALOG.moves,
        type_chart=CATALOG.type_chart,
        companion_mode=True,
        companion_mind=hatch_mind,
        return_context={"source": "breeding_diag_test", "player_instance_id": hatchling_id},
    )

    assert captured
    assert hatchling_id in captured[0]
    assert "ATTACK=" in captured[0] or "learned" in captured[0].lower()
    assert "bond" in captured[0].lower()
