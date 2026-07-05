"""Tests for overworld walk distance egg-step quantization."""

from __future__ import annotations

import pytest

from engine.monster.overworld_egg_steps import (
    MONSTER_EGG_WALK_ACCUMULATOR_KEY,
    OVERWORLD_PIXELS_PER_EGG_STEP,
    record_overworld_walk_distance,
)

pytestmark = pytest.mark.fast


def test_record_overworld_walk_distance_accumulates_fractional_pixels() -> None:
    values: dict = {}
    assert record_overworld_walk_distance(values, 30.0) == 0
    assert values[MONSTER_EGG_WALK_ACCUMULATOR_KEY] == pytest.approx(30.0)
    assert record_overworld_walk_distance(values, 30.0) == 1
    assert values[MONSTER_EGG_WALK_ACCUMULATOR_KEY] == pytest.approx(12.0)


def test_record_overworld_walk_distance_emits_multiple_steps_in_one_call() -> None:
    values: dict = {}
    steps = record_overworld_walk_distance(values, OVERWORLD_PIXELS_PER_EGG_STEP * 3 + 10.0)
    assert steps == 3
    assert values[MONSTER_EGG_WALK_ACCUMULATOR_KEY] == pytest.approx(10.0)
