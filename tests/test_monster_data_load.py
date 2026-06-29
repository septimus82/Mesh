from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from engine.monster.battle_model import MonsterInstance, compute_damage, resolve_move
from engine.monster.battle_controller import controller_from_catalog
from engine.monster.data_load import load_monster_catalog, parse_moves, parse_species, parse_type_chart

pytestmark = pytest.mark.fast


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@pytest.fixture
def valid_fixture_dir(tmp_path: Path) -> Path:
    _write_json(
        tmp_path / "monster_moves.json",
        {
            "moves": [
                {"id": "tackle", "type": "normal", "power": 40, "accuracy": 100, "pp": 35},
                {"id": "ember", "type": "fire", "power": 40, "accuracy": 100, "pp": 25},
            ]
        },
    )
    _write_json(
        tmp_path / "monster_species.json",
        {
            "species": [
                {
                    "id": "sprout",
                    "types": ["grass"],
                    "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                    "learnset": ["tackle", "ember"],
                    "capture_rate": 190,
                    "sprite": "sprites/sprout.png",
                },
                {
                    "id": "turtle",
                    "types": ["water"],
                    "base_stats": {"hp": 32, "atk": 9, "defense": 12, "spd": 6},
                    "learnset": ["tackle"],
                    "capture_rate": 180,
                    "sprite": "sprites/turtle.png",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "monster_type_chart.json",
        {
            "types": ["normal", "fire", "water", "grass"],
            "chart": {
                "fire": {"grass": 2.0, "water": 0.5},
                "grass": {"water": 2.0, "fire": 0.5},
                "water": {"fire": 2.0, "grass": 0.5},
            },
        },
    )
    return tmp_path


def test_module_imports_without_runtime_initialization() -> None:
    module = importlib.import_module("engine.monster.data_load")
    assert module.__name__ == "engine.monster.data_load"
    assert not hasattr(module, "GameWindow")


def test_valid_fixtures_load_catalog_with_expected_counts(valid_fixture_dir: Path) -> None:
    catalog, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is True
    assert result.errors == ()
    assert catalog is not None
    assert len(catalog.species) == 2
    assert len(catalog.moves) == 2
    assert catalog.type_chart["fire"]["grass"] == 2.0
    assert "grass" in catalog.known_types
    assert catalog.species["sprout"].capture_rate == 190


def test_unknown_learnset_move_reports_species_and_move_id(valid_fixture_dir: Path) -> None:
    species_payload = json.loads((valid_fixture_dir / "monster_species.json").read_text(encoding="utf-8"))
    species_payload["species"][0]["learnset"] = ["tackle", "missing_move"]
    _write_json(valid_fixture_dir / "monster_species.json", species_payload)

    catalog, result = load_monster_catalog(valid_fixture_dir)
    assert catalog is None
    assert result.ok is False
    assert any("species 'sprout'" in err and "missing_move" in err for err in result.errors)


def test_unknown_type_in_species_reports_validation_error(valid_fixture_dir: Path) -> None:
    species_payload = json.loads((valid_fixture_dir / "monster_species.json").read_text(encoding="utf-8"))
    species_payload["species"][0]["types"] = ["grass", "shadow"]
    _write_json(valid_fixture_dir / "monster_species.json", species_payload)

    _, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is False
    assert any("shadow" in err for err in result.errors)


def test_unknown_type_in_move_reports_validation_error(valid_fixture_dir: Path) -> None:
    moves_payload = json.loads((valid_fixture_dir / "monster_moves.json").read_text(encoding="utf-8"))
    moves_payload["moves"][1]["type"] = "shadow"
    _write_json(valid_fixture_dir / "monster_moves.json", moves_payload)

    _, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is False
    assert any("shadow" in err for err in result.errors)


def test_unknown_type_in_chart_reports_validation_error(valid_fixture_dir: Path) -> None:
    chart_payload = json.loads((valid_fixture_dir / "monster_type_chart.json").read_text(encoding="utf-8"))
    chart_payload["chart"]["fire"]["shadow"] = 2.0
    _write_json(valid_fixture_dir / "monster_type_chart.json", chart_payload)

    _, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is False
    assert any("shadow" in err for err in result.errors)


def test_duplicate_species_id_reports_error(valid_fixture_dir: Path) -> None:
    species_payload = json.loads((valid_fixture_dir / "monster_species.json").read_text(encoding="utf-8"))
    species_payload["species"].append(species_payload["species"][0])
    _write_json(valid_fixture_dir / "monster_species.json", species_payload)

    _, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is False
    assert any("duplicate species id 'sprout'" in err for err in result.errors)


def test_duplicate_move_id_reports_error(valid_fixture_dir: Path) -> None:
    moves_payload = json.loads((valid_fixture_dir / "monster_moves.json").read_text(encoding="utf-8"))
    moves_payload["moves"].append(moves_payload["moves"][0])
    _write_json(valid_fixture_dir / "monster_moves.json", moves_payload)

    _, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is False
    assert any("duplicate move id 'tackle'" in err for err in result.errors)


def test_loaded_data_feeds_resolve_move_deterministically(valid_fixture_dir: Path) -> None:
    catalog, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is True
    assert catalog is not None

    attacker = MonsterInstance(catalog.species["sprout"], level=10, known_moves=("tackle",))
    defender = MonsterInstance(catalog.species["turtle"], level=10, current_hp=42)
    tackle = catalog.moves["tackle"]

    battle_result = resolve_move(attacker, defender, tackle, catalog.type_chart, rng=None)
    expected = compute_damage(
        level=attacker.level,
        attacker_atk=attacker.stats.atk,
        defender_def=defender.stats.defense,
        move_power=tackle.power,
        type_mult=1.0,
        rng=None,
    )

    assert battle_result.damage == expected
    assert battle_result.defender.current_hp == 42 - expected


def test_learnset_object_entries_load_move_ids(valid_fixture_dir: Path) -> None:
    species_payload = json.loads((valid_fixture_dir / "monster_species.json").read_text(encoding="utf-8"))
    species_payload["species"][0]["learnset"] = [
        {"level": 1, "move_id": "tackle"},
        {"level": 3, "move_id": "ember"},
    ]
    _write_json(valid_fixture_dir / "monster_species.json", species_payload)

    catalog, result = load_monster_catalog(valid_fixture_dir)
    assert result.ok is True
    assert catalog is not None
    assert catalog.species["sprout"].learnset == ("tackle", "ember")


def test_missing_capture_rate_uses_default() -> None:
    species, result = parse_species(
        {
            "species": [
                {
                    "id": "sprout",
                    "types": ["grass"],
                    "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                    "learnset": ["tackle"],
                }
            ]
        }
    )

    assert result.ok is True
    assert species["sprout"].capture_rate == 150


def test_invalid_capture_rate_reports_validation_error(valid_fixture_dir: Path) -> None:
    species_payload = json.loads((valid_fixture_dir / "monster_species.json").read_text(encoding="utf-8"))
    species_payload["species"][0]["capture_rate"] = 999
    _write_json(valid_fixture_dir / "monster_species.json", species_payload)

    _, result = load_monster_catalog(valid_fixture_dir)

    assert result.ok is False
    assert any("capture_rate" in err and "between 1 and 255" in err for err in result.errors)


def test_move_status_inflict_parses_and_validates() -> None:
    moves, ok_result = parse_moves(
        {
            "moves": [
                {
                    "id": "sleep_powder",
                    "type": "normal",
                    "power": 0,
                    "accuracy": 100,
                    "pp": 15,
                    "status_inflict": {"condition": "sleep", "chance": 0.75},
                }
            ]
        }
    )
    assert ok_result.ok is True
    assert moves["sleep_powder"].status_inflict is not None
    assert moves["sleep_powder"].status_inflict.condition == "sleep"
    assert moves["sleep_powder"].status_inflict.chance == 0.75

    _, bad_result = parse_moves(
        {
            "moves": [
                {
                    "id": "bad",
                    "type": "normal",
                    "power": 0,
                    "accuracy": 100,
                    "pp": 15,
                    "status_inflict": {"condition": "burn", "chance": 1.5},
                }
            ]
        }
    )
    assert bad_result.ok is False
    assert any("status_inflict" in err for err in bad_result.errors)


def test_repo_catalog_loads_status_moves_and_learnsets() -> None:
    catalog, result = load_monster_catalog(Path("assets/data"))

    assert result.ok is True
    assert catalog is not None
    assert "poison_sting" in catalog.moves
    assert "sleep_powder" in catalog.moves

    poison = catalog.moves["poison_sting"]
    sleep = catalog.moves["sleep_powder"]
    assert poison.status_inflict is not None
    assert poison.status_inflict.condition == "poison"
    assert poison.status_inflict.chance == 0.5
    assert sleep.status_inflict is not None
    assert sleep.status_inflict.condition == "sleep"
    assert sleep.status_inflict.chance == 0.75

    assert "poison_sting" in catalog.species["sproutling"].learnset
    assert "sleep_powder" in catalog.species["sproutling"].learnset
    assert "sleep_powder" in catalog.species["shelltide"].learnset


class _Rng:
    def __init__(self, *values: float) -> None:
        self.values = list(values)

    def random(self) -> float:
        return self.values.pop(0) if self.values else 0.0


def test_catalog_poison_sting_inflicts_poison_under_fixed_seed() -> None:
    catalog, result = load_monster_catalog(Path("assets/data"))
    assert result.ok is True
    assert catalog is not None

    controller = controller_from_catalog(
        catalog,
        player=MonsterInstance(catalog.species["sproutling"], level=10, known_moves=("poison_sting",)),
        opponent=MonsterInstance(catalog.species["shelltide"], level=10, known_moves=("tackle",)),
        rng=_Rng(0.0, 0.0, 0.0),
        opponent_action_provider=lambda _controller: "tackle",
    )

    controller.submit_action("player", "poison_sting")

    assert controller.opponent.status_condition == "poison"
    assert any(entry.status_event == "poisoned" for entry in controller.turn_log if entry.kind == "status")


def test_catalog_sleep_powder_inflicts_sleep_under_fixed_seed() -> None:
    catalog, result = load_monster_catalog(Path("assets/data"))
    assert result.ok is True
    assert catalog is not None

    controller = controller_from_catalog(
        catalog,
        player=MonsterInstance(catalog.species["sproutling"], level=10, known_moves=("sleep_powder",)),
        opponent=MonsterInstance(catalog.species["shelltide"], level=10, known_moves=("tackle",)),
        rng=_Rng(0.0, 0.0, 0.0),
        opponent_action_provider=lambda _controller: "tackle",
    )

    controller.submit_action("player", "sleep_powder")

    assert controller.opponent.status_condition == "sleep"
    assert any(entry.status_event == "fell_asleep" for entry in controller.turn_log if entry.kind == "status")


def test_parse_helpers_accept_inline_payloads() -> None:
    moves, move_result = parse_moves({"moves": [{"id": "tackle", "type": "normal", "power": 40, "accuracy": 100, "pp": 35}]})
    species, species_result = parse_species(
        {
            "species": [
                {
                    "id": "sprout",
                    "types": ["grass"],
                    "base_stats": {"hp": 30, "atk": 10, "defense": 10, "spd": 8},
                    "learnset": ["tackle"],
                }
            ]
        }
    )
    chart, known_types, chart_result = parse_type_chart(
        {"types": ["normal", "grass"], "chart": {"normal": {"grass": 1.0}}}
    )

    assert move_result.ok and species_result.ok and chart_result.ok
    assert "tackle" in moves
    assert "sprout" in species
    assert "normal" in known_types
