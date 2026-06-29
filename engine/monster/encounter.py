"""Monster encounter-table helpers for overworld triggers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .battle_model import MonsterInstance
from .data_load import MonsterCatalog


class RandomLike(Protocol):
    def random(self) -> float:
        ...


@dataclass(frozen=True, slots=True)
class EncounterRollResult:
    ok: bool
    errors: tuple[str, ...] = ()
    species_id: str | None = None
    level: int | None = None
    monster: MonsterInstance | None = None
    entry_index: int | None = None


def roll_monster_encounter(
    table: Any,
    catalog: MonsterCatalog,
    rng: RandomLike,
) -> EncounterRollResult:
    """Validate and roll a weighted encounter table."""

    rows, errors = _validate_table(table, catalog)
    if errors:
        return EncounterRollResult(ok=False, errors=tuple(errors))
    if not rows:
        return EncounterRollResult(ok=False, errors=("encounter_table must contain at least one entry",))

    total_weight = sum(float(row["weight"]) for row in rows)
    target = max(0.0, min(1.0, float(rng.random()))) * total_weight
    cursor = 0.0
    chosen = rows[-1]
    for row in rows:
        cursor += float(row["weight"])
        if target < cursor:
            chosen = row
            break

    level = _roll_level(chosen, rng)
    species_id = str(chosen["species_id"])
    species = catalog.species[species_id]
    monster = MonsterInstance(species, level=level, known_moves=species.learnset)
    return EncounterRollResult(
        ok=True,
        species_id=species_id,
        level=level,
        monster=monster,
        entry_index=int(chosen["index"]),
    )


def _validate_table(table: Any, catalog: MonsterCatalog) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(table, list):
        return [], ["encounter_table must be a list"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, entry in enumerate(table):
        label = f"encounter_table[{index}]"
        if not isinstance(entry, Mapping):
            errors.append(f"{label} must be an object")
            continue
        species_id = entry.get("species_id")
        if not isinstance(species_id, str) or not species_id.strip():
            errors.append(f"{label}.species_id must be a non-empty string")
            continue
        species_id = species_id.strip()
        if species_id not in catalog.species:
            errors.append(f"{label}.species_id references unknown species '{species_id}'")
            continue

        weight = _coerce_positive_number(entry.get("weight", 1), f"{label}.weight", errors)
        if weight is None:
            continue
        level_info = _normalize_level(entry, label, errors)
        if level_info is None:
            continue
        rows.append({"index": index, "species_id": species_id, "weight": weight, **level_info})
    return rows, errors


def _coerce_positive_number(value: Any, label: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{label} must be a positive number")
        return None
    numeric = float(value)
    if numeric <= 0.0:
        errors.append(f"{label} must be greater than 0")
        return None
    return numeric


def _normalize_level(entry: Mapping[str, Any], label: str, errors: list[str]) -> dict[str, int] | None:
    if "level" in entry:
        level = _coerce_level(entry.get("level"), f"{label}.level", errors)
        return {"min_level": level, "max_level": level} if level is not None else None

    min_level = _coerce_level(entry.get("min_level"), f"{label}.min_level", errors)
    max_level = _coerce_level(entry.get("max_level"), f"{label}.max_level", errors)
    if min_level is None or max_level is None:
        return None
    if min_level > max_level:
        errors.append(f"{label}.min_level must be <= max_level")
        return None
    return {"min_level": min_level, "max_level": max_level}


def _coerce_level(value: Any, label: str, errors: list[str]) -> int | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{label} must be a positive integer")
        return None
    level = int(value)
    if level <= 0:
        errors.append(f"{label} must be greater than 0")
        return None
    return level


def _roll_level(row: Mapping[str, Any], rng: RandomLike) -> int:
    min_level = int(row["min_level"])
    max_level = int(row["max_level"])
    if min_level == max_level:
        return min_level
    span = max_level - min_level + 1
    offset = int(max(0.0, min(0.999999, float(rng.random()))) * span)
    return min_level + offset
