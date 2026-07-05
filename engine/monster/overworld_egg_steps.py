"""Overworld walk distance quantization for egg incubation."""

from __future__ import annotations

from typing import Any, MutableMapping

OVERWORLD_PIXELS_PER_EGG_STEP = 48
MONSTER_EGG_WALK_ACCUMULATOR_KEY = "monster_egg_walk_accumulator"


def record_overworld_walk_distance(values: MutableMapping[str, Any], distance_px: float) -> int:
    """Accumulate walked pixels and return whole egg steps earned."""

    walked = max(0.0, float(distance_px))
    if walked <= 0.0:
        return 0
    accumulated = float(values.get(MONSTER_EGG_WALK_ACCUMULATOR_KEY, 0.0) or 0.0) + walked
    steps = int(accumulated // OVERWORLD_PIXELS_PER_EGG_STEP)
    values[MONSTER_EGG_WALK_ACCUMULATOR_KEY] = accumulated - (steps * OVERWORLD_PIXELS_PER_EGG_STEP)
    return steps
