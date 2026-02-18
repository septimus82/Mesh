from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

EntityId: TypeAlias = str
ScenePath: TypeAlias = str | Path
Vec2: TypeAlias = tuple[float, float]

__all__ = ["EntityId", "ScenePath", "Vec2"]

