"""Load and validate authored monster battle JSON data.

Pure module: no GameWindow, scenes, save, event bus, UI, or arcade imports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .battle_model import BattleSprite, BattleStats, Move, MoveStatusInflict, Species, TypeChart

DEFAULT_DATA_DIR = Path("assets/data")
SPECIES_FILENAME = "monster_species.json"
MOVES_FILENAME = "monster_moves.json"
TYPE_CHART_FILENAME = "monster_type_chart.json"
DEFAULT_CAPTURE_RATE = 150
MIN_CAPTURE_RATE = 1
MAX_CAPTURE_RATE = 255
KNOWN_STATUS_CONDITIONS = frozenset({"poison", "sleep"})


@dataclass(frozen=True, slots=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors)}


@dataclass(frozen=True, slots=True)
class MonsterCatalog:
    species: dict[str, Species]
    moves: dict[str, Move]
    type_chart: TypeChart
    known_types: frozenset[str]


def _merge_results(*results: ValidationResult) -> ValidationResult:
    errors: list[str] = []
    for result in results:
        errors.extend(result.errors)
    return ValidationResult(ok=not errors, errors=tuple(errors))


def _read_json(path: Path) -> tuple[Any | None, ValidationResult]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, ValidationResult(ok=False, errors=(f"{path}: failed to read file: {exc}",))
    except json.JSONDecodeError as exc:
        return None, ValidationResult(ok=False, errors=(f"{path}: invalid JSON: {exc}",))
    return payload, ValidationResult(ok=True)


def _require_mapping(value: Any, *, label: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, dict):
        return None, f"{label} must be a JSON object"
    return value, None


def _parse_base_stats(raw: Any, *, label: str) -> tuple[BattleStats | None, str | None]:
    mapping, err = _require_mapping(raw, label=f"{label}.base_stats")
    if err is not None:
        return None, err

    def _int_field(*keys: str, default: int | None = None) -> tuple[int | None, str | None]:
        for key in keys:
            if key in mapping:
                value = mapping[key]
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    return None, f"{label}.base_stats.{key} must be a number"
                return int(value), None
        if default is not None:
            return default, None
        return None, f"{label}.base_stats missing required stat (expected one of: {', '.join(keys)})"

    hp, err = _int_field("hp")
    if err:
        return None, err
    atk, err = _int_field("atk", "attack")
    if err:
        return None, err
    defense, err = _int_field("defense")
    if err:
        return None, err
    spd, err = _int_field("spd", "speed")
    if err:
        return None, err
    return BattleStats(hp=hp, atk=atk, defense=defense, spd=spd), None


def _parse_learnset(raw: Any, *, label: str) -> tuple[tuple[str, ...], str | None]:
    if raw is None:
        return (), None
    if not isinstance(raw, list):
        return (), f"{label}.learnset must be a list"
    move_ids: list[str] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, str):
            move_id = entry.strip()
            if not move_id:
                return (), f"{label}.learnset[{index}] must be a non-empty move id"
            move_ids.append(move_id)
            continue
        if isinstance(entry, dict):
            move_id = entry.get("move_id")
            if not isinstance(move_id, str) or not move_id.strip():
                return (), f"{label}.learnset[{index}].move_id must be a non-empty string"
            move_ids.append(move_id.strip())
            continue
        return (), f"{label}.learnset[{index}] must be a move id string or object with move_id"
    return tuple(move_ids), None


def _parse_capture_rate(raw: Any, *, label: str) -> tuple[int, str | None]:
    if raw is None:
        return DEFAULT_CAPTURE_RATE, None
    if not isinstance(raw, (int, float)) or isinstance(raw, bool):
        return DEFAULT_CAPTURE_RATE, f"{label}.capture_rate must be a number"
    value = int(raw)
    if value < MIN_CAPTURE_RATE or value > MAX_CAPTURE_RATE:
        return DEFAULT_CAPTURE_RATE, f"{label}.capture_rate must be between {MIN_CAPTURE_RATE} and {MAX_CAPTURE_RATE}"
    return value, None


def _parse_battle_sprite(raw: Any, *, label: str) -> tuple[BattleSprite | None, str | None]:
    if raw is None:
        return None, None
    mapping, err = _require_mapping(raw, label=f"{label}.battle_sprite")
    if err is not None:
        return None, err

    sheet = mapping.get("sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        return None, f"{label}.battle_sprite.sheet must be a non-empty string"

    def _positive_int(field: str) -> tuple[int | None, str | None]:
        value = mapping.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None, f"{label}.battle_sprite.{field} must be a positive number"
        parsed = int(value)
        if parsed <= 0:
            return None, f"{label}.battle_sprite.{field} must be a positive number"
        return parsed, None

    columns, err = _positive_int("columns")
    if err:
        return None, err
    rows, err = _positive_int("rows")
    if err:
        return None, err
    frame_width, err = _positive_int("frame_width")
    if err:
        return None, err
    frame_height, err = _positive_int("frame_height")
    if err:
        return None, err

    idle_raw = mapping.get("idle_frames")
    if not isinstance(idle_raw, list) or not idle_raw:
        return None, f"{label}.battle_sprite.idle_frames must be a non-empty list of frame indices"
    idle_frames: list[int] = []
    for index, entry in enumerate(idle_raw):
        if not isinstance(entry, (int, float)) or isinstance(entry, bool):
            return None, f"{label}.battle_sprite.idle_frames[{index}] must be a number"
        idle_frames.append(int(entry))

    fps_raw = mapping.get("fps", 6)
    if not isinstance(fps_raw, (int, float)) or isinstance(fps_raw, bool):
        return None, f"{label}.battle_sprite.fps must be a number"
    fps = float(fps_raw)
    if fps <= 0.0:
        return None, f"{label}.battle_sprite.fps must be greater than 0"

    return (
        BattleSprite(
            sheet=sheet.strip(),
            columns=int(columns),
            rows=int(rows),
            frame_width=int(frame_width),
            frame_height=int(frame_height),
            idle_frames=tuple(idle_frames),
            fps=fps,
        ),
        None,
    )


def _parse_status_inflict(raw: Any, *, label: str) -> tuple[MoveStatusInflict | None, str | None]:
    if raw is None:
        return None, None
    mapping, err = _require_mapping(raw, label=f"{label}.status_inflict")
    if err is not None:
        return None, err
    condition = mapping.get("condition")
    if not isinstance(condition, str) or condition.strip() not in KNOWN_STATUS_CONDITIONS:
        return None, f"{label}.status_inflict.condition must be one of: {', '.join(sorted(KNOWN_STATUS_CONDITIONS))}"
    chance = mapping.get("chance")
    if not isinstance(chance, (int, float)) or isinstance(chance, bool):
        return None, f"{label}.status_inflict.chance must be a number"
    chance_value = float(chance)
    if chance_value < 0.0 or chance_value > 1.0:
        return None, f"{label}.status_inflict.chance must be between 0 and 1"
    return MoveStatusInflict(condition=condition.strip(), chance=chance_value), None


def parse_moves(payload: Any, *, source: str = "moves") -> tuple[dict[str, Move], ValidationResult]:
    root, err = _require_mapping(payload, label=source)
    if err is not None:
        return {}, ValidationResult(ok=False, errors=(err,))

    rows = root.get("moves")
    if rows is None:
        return {}, ValidationResult(ok=False, errors=(f"{source}: missing 'moves' array",))
    if not isinstance(rows, list):
        return {}, ValidationResult(ok=False, errors=(f"{source}.moves must be a list",))

    moves: dict[str, Move] = {}
    errors: list[str] = []
    for index, row in enumerate(rows):
        label = f"{source}.moves[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        move_id = row.get("id")
        if not isinstance(move_id, str) or not move_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
            continue
        move_id = move_id.strip()
        if move_id in moves:
            errors.append(f"{source}: duplicate move id '{move_id}'")
            continue
        move_type = row.get("type")
        if not isinstance(move_type, str) or not move_type.strip():
            errors.append(f"{label}.type must be a non-empty string")
            continue
        for field in ("power", "accuracy", "pp"):
            value = row.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"{label}.{field} must be a number")
                break
        else:
            status_inflict, status_err = _parse_status_inflict(row.get("status_inflict"), label=label)
            if status_err is not None:
                errors.append(status_err)
                continue
            moves[move_id] = Move(
                id=move_id,
                type=move_type.strip(),
                power=int(row["power"]),
                accuracy=int(row["accuracy"]),
                pp=int(row["pp"]),
                status_inflict=status_inflict,
            )
    return moves, ValidationResult(ok=not errors, errors=tuple(errors))


def parse_species(payload: Any, *, source: str = "species") -> tuple[dict[str, Species], ValidationResult]:
    root, err = _require_mapping(payload, label=source)
    if err is not None:
        return {}, ValidationResult(ok=False, errors=(err,))

    rows = root.get("species")
    if rows is None:
        return {}, ValidationResult(ok=False, errors=(f"{source}: missing 'species' array",))
    if not isinstance(rows, list):
        return {}, ValidationResult(ok=False, errors=(f"{source}.species must be a list",))

    species: dict[str, Species] = {}
    errors: list[str] = []
    for index, row in enumerate(rows):
        label = f"{source}.species[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        species_id = row.get("id")
        if not isinstance(species_id, str) or not species_id.strip():
            errors.append(f"{label}.id must be a non-empty string")
            continue
        species_id = species_id.strip()
        if species_id in species:
            errors.append(f"{source}: duplicate species id '{species_id}'")
            continue
        types_raw = row.get("types")
        if not isinstance(types_raw, list) or not types_raw:
            errors.append(f"{label}.types must be a non-empty list of strings")
            continue
        types: list[str] = []
        type_err = False
        for type_index, entry in enumerate(types_raw):
            if not isinstance(entry, str) or not entry.strip():
                errors.append(f"{label}.types[{type_index}] must be a non-empty string")
                type_err = True
                break
            types.append(entry.strip())
        if type_err:
            continue
        stats, stats_err = _parse_base_stats(row.get("base_stats"), label=label)
        if stats_err:
            errors.append(stats_err)
            continue
        learnset, learn_err = _parse_learnset(row.get("learnset"), label=label)
        if learn_err:
            errors.append(learn_err)
            continue
        capture_rate, capture_err = _parse_capture_rate(row.get("capture_rate"), label=label)
        if capture_err:
            errors.append(capture_err)
            continue
        battle_sprite, battle_sprite_err = _parse_battle_sprite(row.get("battle_sprite"), label=label)
        if battle_sprite_err:
            errors.append(battle_sprite_err)
            continue
        species[species_id] = Species(
            id=species_id,
            base_stats=stats,
            types=tuple(types),
            learnset=learnset,
            capture_rate=capture_rate,
            battle_sprite=battle_sprite,
        )
    return species, ValidationResult(ok=not errors, errors=tuple(errors))


def parse_type_chart(payload: Any, *, source: str = "type_chart") -> tuple[TypeChart, frozenset[str], ValidationResult]:
    root, err = _require_mapping(payload, label=source)
    if err is not None:
        return {}, frozenset(), ValidationResult(ok=False, errors=(err,))

    known_types_raw = root.get("types")
    if "chart" in root:
        chart_raw = root["chart"]
    else:
        chart_raw = {key: value for key, value in root.items() if key != "types"}

    known_types: set[str] = set()
    errors: list[str] = []
    explicit_types = known_types_raw is not None
    if known_types_raw is not None:
        if not isinstance(known_types_raw, list):
            errors.append(f"{source}.types must be a list of strings when present")
        else:
            for index, entry in enumerate(known_types_raw):
                if not isinstance(entry, str) or not entry.strip():
                    errors.append(f"{source}.types[{index}] must be a non-empty string")
                else:
                    known_types.add(entry.strip())

    if not isinstance(chart_raw, dict):
        errors.append(f"{source}.chart must be an object")
        return {}, frozenset(known_types), ValidationResult(ok=False, errors=tuple(errors))

    chart: dict[str, dict[str, float]] = {}
    for attack_type, defenders in chart_raw.items():
        if attack_type == "types":
            continue
        if not isinstance(attack_type, str) or not attack_type.strip():
            errors.append(f"{source}.chart has a non-string attacking type key")
            continue
        attack_key = attack_type.strip()
        if not explicit_types:
            known_types.add(attack_key)
        if not isinstance(defenders, dict):
            errors.append(f"{source}.chart['{attack_key}'] must be an object")
            continue
        row: dict[str, float] = {}
        for defend_type, multiplier in defenders.items():
            if not isinstance(defend_type, str) or not defend_type.strip():
                errors.append(f"{source}.chart['{attack_key}'] has a non-string defending type key")
                continue
            if not isinstance(multiplier, (int, float)) or isinstance(multiplier, bool):
                errors.append(
                    f"{source}.chart['{attack_key}']['{defend_type}'] must be a number",
                )
                continue
            defend_key = defend_type.strip()
            if not explicit_types:
                known_types.add(defend_key)
            row[defend_key] = float(multiplier)
        chart[attack_key] = row

    return chart, frozenset(known_types), ValidationResult(ok=not errors, errors=tuple(errors))


def validate_referential_integrity(
    *,
    species: Mapping[str, Species],
    moves: Mapping[str, Move],
    type_chart: TypeChart,
    known_types: frozenset[str],
    source: str = "catalog",
) -> ValidationResult:
    errors: list[str] = []

    if not known_types:
        derived: set[str] = set()
        for move in moves.values():
            derived.add(move.type)
        for sp in species.values():
            derived.update(sp.types)
        for attack_type, defenders in type_chart.items():
            derived.add(str(attack_type))
            derived.update(str(defend_type) for defend_type in defenders)
        known_types = frozenset(derived)

    for move_id, move in moves.items():
        if move.type not in known_types:
            errors.append(f"{source}: move '{move_id}' references unknown type '{move.type}'")

    for species_id, sp in species.items():
        for move_id in sp.learnset:
            if move_id not in moves:
                errors.append(
                    f"{source}: species '{species_id}' learnset references unknown move '{move_id}'",
                )
        for type_id in sp.types:
            if type_id not in known_types:
                errors.append(f"{source}: species '{species_id}' references unknown type '{type_id}'")

    for attack_type, defenders in type_chart.items():
        if attack_type not in known_types:
            errors.append(f"{source}: type chart references unknown attacking type '{attack_type}'")
        for defend_type in defenders:
            if defend_type not in known_types:
                errors.append(
                    f"{source}: type chart['{attack_type}'] references unknown defending type '{defend_type}'",
                )

    return ValidationResult(ok=not errors, errors=tuple(errors))


def load_moves(path: Path) -> tuple[dict[str, Move], ValidationResult]:
    payload, read_result = _read_json(path)
    if not read_result.ok or payload is None:
        return {}, read_result
    moves, parse_result = parse_moves(payload, source=str(path))
    return moves, _merge_results(read_result, parse_result)


def load_species(path: Path) -> tuple[dict[str, Species], ValidationResult]:
    payload, read_result = _read_json(path)
    if not read_result.ok or payload is None:
        return {}, read_result
    species, parse_result = parse_species(payload, source=str(path))
    return species, _merge_results(read_result, parse_result)


def load_type_chart(path: Path) -> tuple[TypeChart, frozenset[str], ValidationResult]:
    payload, read_result = _read_json(path)
    if not read_result.ok or payload is None:
        return {}, frozenset(), read_result
    chart, known_types, parse_result = parse_type_chart(payload, source=str(path))
    return chart, known_types, _merge_results(read_result, parse_result)


def load_monster_catalog(data_dir: Path | str | None = None) -> tuple[MonsterCatalog | None, ValidationResult]:
    """Load species, moves, and type chart from a directory of JSON files."""

    base = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    moves, moves_result = load_moves(base / MOVES_FILENAME)
    species, species_result = load_species(base / SPECIES_FILENAME)
    type_chart, known_types, chart_result = load_type_chart(base / TYPE_CHART_FILENAME)

    parse_result = _merge_results(moves_result, species_result, chart_result)
    if not parse_result.ok:
        return None, parse_result

    integrity = validate_referential_integrity(
        species=species,
        moves=moves,
        type_chart=type_chart,
        known_types=known_types,
        source=str(base),
    )
    final = _merge_results(parse_result, integrity)
    if not final.ok:
        return None, final

    return MonsterCatalog(
        species=species,
        moves=moves,
        type_chart=type_chart,
        known_types=known_types,
    ), final
