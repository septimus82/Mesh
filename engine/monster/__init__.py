"""Pure monster battle domain model.

This package intentionally stays independent of the Mesh runtime stack.
"""

from __future__ import annotations

from .battle_controller import (
    BattleLogEntry,
    BattlePhase,
    BattleResult,
    BattleSideId,
    InvalidBattleActionError,
    MonsterBattleController,
    MoveAction,
    controller_from_catalog,
)
from .battle_mode import (
    MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT,
    MONSTER_BATTLE_ENDED_EVENT,
    MONSTER_BATTLE_RESULT_KEY,
    MONSTER_BATTLE_RETURN_CONTEXT_KEY,
    MonsterBattleMode,
    MonsterBattleOverlay,
    start_monster_battle,
)
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
    "BattleLogEntry",
    "BattlePhase",
    "BattleResult",
    "BattleSideId",
    "InvalidBattleActionError",
    "MONSTER_BATTLE_CAPTURE_ATTEMPT_EVENT",
    "MONSTER_BATTLE_ENDED_EVENT",
    "MONSTER_BATTLE_RESULT_KEY",
    "MONSTER_BATTLE_RETURN_CONTEXT_KEY",
    "MonsterCatalog",
    "MonsterBattleController",
    "MonsterBattleMode",
    "MonsterBattleOverlay",
    "Move",
    "MoveAction",
    "MoveResolution",
    "MonsterInstance",
    "Species",
    "TypeChart",
    "ValidationResult",
    "compute_damage",
    "controller_from_catalog",
    "load_monster_catalog",
    "load_moves",
    "load_species",
    "load_type_chart",
    "parse_moves",
    "parse_species",
    "parse_type_chart",
    "resolve_move",
    "start_monster_battle",
    "type_multiplier",
    "validate_referential_integrity",
]
