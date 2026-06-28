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

__all__ = [
    "BattleStats",
    "Move",
    "MoveResolution",
    "MonsterInstance",
    "Species",
    "TypeChart",
    "compute_damage",
    "resolve_move",
    "type_multiplier",
]
