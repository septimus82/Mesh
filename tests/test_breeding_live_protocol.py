"""Headless live-protocol transcript for breeding shrine (spike terms path)."""

from __future__ import annotations

import json
import os
import random
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.behaviours.breeding_shrine_zone import BreedingShrineZoneBehaviour
from engine.companion_diagnostics import log_companion_battle_start
from engine.game_state_controller import GameStateController
from engine.monster.battle_mode import MonsterBattleMode
from engine.monster.battle_model import BattleStats, MonsterInstance, Move, Species
from engine.monster.breeding import BORN_INTO_CARE_BOND, BORN_INTO_CARE_TRUST, BreedingParent, breed_offspring
from engine.monster.collection import (
    MONSTER_PARTY_KEY,
    add_caught_monster,
    companion_mind_to_dict,
    ensure_monster_collection,
    load_battle_party_from_values,
    load_companion_mind_for_instance,
)
from engine.monster.companion_mind import CompanionMind, LearnedWeights, Temperament, praise
from engine.monster.data_load import load_battle_terms, load_monster_catalog
from engine.monster.egg_lifecycle import MONSTER_EGGS_KEY, STEPS_REMAINING_KEY, create_breeding_egg
from engine.monster.overworld_egg_steps import OVERWORLD_PIXELS_PER_EGG_STEP
from engine.savegame import load_quick_snapshot, save_quick_snapshot

pytestmark = pytest.mark.fast

SPIKE_ROOT = Path(__file__).resolve().parents[1].parent / "monster_minimal_spike"
TACKLE = Move(id="tackle", type="normal", power=40, accuracy=100, pp=35)
SPROUT = Species(
    id="sproutling",
    base_stats=BattleStats(hp=30, atk=12, defense=10, spd=20),
    types=("grass",),
    learnset=("tackle",),
)
SHELL = Species(
    id="shelltide",
    base_stats=BattleStats(hp=32, atk=9, defense=12, spd=6),
    types=("water",),
    learnset=("tackle",),
)


def _train_bond(mind: CompanionMind, target: float = 50.0) -> CompanionMind:
    trained = mind
    while trained.bond < target:
        trained = praise(trained)
    return trained


def _window(*, catalog: object) -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.paused = False
    window.monster_battle_mode_active = False
    window.ui_controller = types.SimpleNamespace(ui_elements=[], register_ui_element=lambda _element: None)
    window.emit_event = MagicMock()
    window.console_log = MagicMock()
    window.game_state_controller = GameStateController(window)
    window.monster_catalog = catalog
    window.scene_controller = types.SimpleNamespace(current_scene_path="packs/core_regions/scenes/start.json")
    window.engine_config = types.SimpleNamespace(world_file="packs/core_regions/worlds/main.json")
    window.find_sprite_by_name = MagicMock(
        return_value=types.SimpleNamespace(center_x=710.0, center_y=425.0, mesh_name="Player"),
    )
    return window


@pytest.mark.skipif(not SPIKE_ROOT.is_dir(), reason="monster_minimal_spike not present beside Mesh")
def test_breeding_live_protocol_transcript(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    os.environ["MESH_COMPANION_DIAG"] = "1"
    data_dir = SPIKE_ROOT / "assets" / "data"
    catalog, catalog_result = load_monster_catalog(data_dir)
    terms, terms_result = load_battle_terms(data_dir)
    assert catalog_result.ok and catalog is not None
    assert terms_result.ok

    window = _window(catalog=catalog)
    window.battle_terms = terms
    values = window.game_state_controller.state.values
    ensure_monster_collection(values)
    sprout = add_caught_monster(values, MonsterInstance(SPROUT, level=8, known_moves=SPROUT.learnset))
    shell = add_caught_monster(values, MonsterInstance(SHELL, level=7, known_moves=SHELL.learnset))
    parent_a_mind = _train_bond(
        CompanionMind(
            temperament=Temperament(aggression=65.0, fear=18.0),
            learned=LearnedWeights(ATTACK=22.0, DEFEND=8.0, HESITATE=4.0),
            bond=15.0,
            traits=("brave",),
        ),
    )
    parent_b_mind = _train_bond(
        CompanionMind(
            temperament=Temperament(aggression=28.0, fear=42.0),
            learned=LearnedWeights(ATTACK=12.0, DEFEND=16.0, HESITATE=6.0),
            bond=15.0,
            traits=("timid",),
        ),
    )
    values["monster_instances"][sprout.instance_id]["companion_mind"] = companion_mind_to_dict(parent_a_mind)
    values["monster_instances"][shell.instance_id]["companion_mind"] = companion_mind_to_dict(parent_b_mind)

    mid_values: dict = {}
    ensure_monster_collection(mid_values)
    mid_values[MONSTER_PARTY_KEY] = list(values[MONSTER_PARTY_KEY])
    mid_values["monster_instances"] = json.loads(json.dumps(values["monster_instances"]))
    mid_offspring, mid_mind = breed_offspring(
        BreedingParent(MonsterInstance(SPROUT, level=8, known_moves=SPROUT.learnset), parent_a_mind),
        BreedingParent(MonsterInstance(SHELL, level=7, known_moves=SHELL.learnset), parent_b_mind),
        random.Random(7),
    )
    create_breeding_egg(mid_values, offspring=mid_offspring, mind=mid_mind, hatch_steps=120)
    save_path = tmp_path / "breeding_probe_quick.json"
    mid_window = _window(catalog=catalog)
    mid_window.game_state_controller.state.values = mid_values
    assert save_quick_snapshot(mid_window, path=save_path) is True
    reload_window = _window(catalog=catalog)
    reload_window.game_state_controller.state.values = {}
    assert load_quick_snapshot(reload_window, path=save_path) is True
    reloaded_steps = reload_window.game_state_controller.state.values[MONSTER_EGGS_KEY][0][STEPS_REMAINING_KEY]
    assert reloaded_steps == 120

    shrine = BreedingShrineZoneBehaviour(
        types.SimpleNamespace(center_x=701.0, center_y=420.0, mesh_name="Sakura Breeding Shrine", mesh_id="shrine"),
        window,
        trigger_radius=80.0,
        trigger_target="Player",
        bond_threshold=50.0,
        hatch_steps=4,
        cooldown_seconds=0.0,
        rng=random.Random(7),
    )
    shrine.update(0.016)
    egg_created_line = str(window.console_log.call_args.args[0])

    for _ in range(4):
        window.game_state_controller.record_overworld_walk_distance(OVERWORLD_PIXELS_PER_EGG_STEP)

    hatchling_id = list(values[MONSTER_PARTY_KEY])[-1]
    display = str(values["monster_instances"][hatchling_id]["species_id"]).replace("_", " ").title()
    hatched_line = terms.format_egg_hatched(name=display)
    hatch_mind = load_companion_mind_for_instance(values, hatchling_id)
    assert hatch_mind is not None
    assert hatch_mind.bond == pytest.approx(BORN_INTO_CARE_BOND)
    assert hatch_mind.trust == pytest.approx(BORN_INTO_CARE_TRUST)

    party, party_instance_ids = load_battle_party_from_values(
        values,
        catalog.species,
        fallback=MonsterInstance(SPROUT, level=1, known_moves=SPROUT.learnset),
    )
    hatch_index = party_instance_ids.index(hatchling_id)
    hatchling = party[hatch_index]
    party = [hatchling, *[monster for index, monster in enumerate(party) if index != hatch_index]]
    party_instance_ids = [hatchling_id, *[item for index, item in enumerate(party_instance_ids) if index != hatch_index]]

    mode = MonsterBattleMode(window)  # type: ignore[arg-type]
    window.monster_battle_mode = mode
    mode.start_battle(
        player_monster=hatchling,
        player_party=party,
        player_party_instance_ids=party_instance_ids,
        opponent_monster=MonsterInstance(SHELL, level=6, current_hp=30, known_moves=SHELL.learnset),
        moves={"tackle": TACKLE},
        type_chart=catalog.type_chart,
        companion_mode=True,
        companion_mind=hatch_mind,
        return_context={"source": "breeding_probe", "player_instance_id": hatchling_id},
    )

    with capsys.disabled():
        log_companion_battle_start(
            instance_id=hatchling_id,
            source="saved",
            mind=hatch_mind,
            trigger="breeding_probe",
        )

    print(f"EGG_CREATED_LINE: {egg_created_line}")
    print(f"EGG_HATCHED_LINE: {hatched_line}")
    print(f"MID_INCUBATION_STEPS_REMAINING_AFTER_F5: {reloaded_steps}")
    print(f"PARTY_AFTER_HATCH: {list(values[MONSTER_PARTY_KEY])}")
