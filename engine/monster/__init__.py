"""Pure monster battle domain model.

This package intentionally stays independent of the Mesh runtime stack.
"""

from __future__ import annotations

from .battle_model import (
    BattleStats,
    MonsterInstance,
    Move,
    MoveResolution,
    Species,
    TypeChart,
    compute_damage,
    resolve_move,
    type_multiplier,
)
from .data_load import (
    MonsterCatalog,
    ValidationResult,
    load_monster_catalog,
    load_moves,
    load_species,
    load_type_chart,
    parse_moves,
    parse_species,
    parse_type_chart,
    validate_referential_integrity,
)

__all__ = [
    "BattleStats",
    "MonsterCatalog",
    "Move",
    "MoveResolution",
    "MonsterInstance",
    "Species",
    "TypeChart",
    "ValidationResult",
    "compute_damage",
    "load_monster_catalog",
    "load_moves",
    "load_species",
    "load_type_chart",
    "parse_moves",
    "parse_species",
    "parse_type_chart",
    "resolve_move",
    "type_multiplier",
    "validate_referential_integrity",
]
