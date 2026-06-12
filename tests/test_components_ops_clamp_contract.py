"""Contract tests for components_ops.py clamp and wrap helpers.

Tests cover:
- radius clamp
- flicker clamp
- rotation wrap
- rgba clamp
- apply_inspector_delta with constraints
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from engine.editor.components_model import (
    LIGHT_DEFAULTS,
    TRANSFORM_DEFAULTS,
)
from engine.editor.components_ops import (
    apply_inspector_delta,
    clamp_float,
    clamp_int,
    clamp_rgba,
    cycle_enum_value,
    get_step_for_field,
    reset_field_to_default,
    wrap_deg,
)

# -----------------------------------------------------------------------------
# Test clamp_float
# -----------------------------------------------------------------------------

class TestClampFloat:
    """Test clamp_float function."""

    def test_clamp_no_bounds(self):
        """No bounds should return original value."""
        assert clamp_float(100.0) == 100.0
        assert clamp_float(-100.0) == -100.0

    def test_clamp_min_only(self):
        """Min bound only."""
        assert clamp_float(5.0, lo=10.0) == 10.0
        assert clamp_float(15.0, lo=10.0) == 15.0

    def test_clamp_max_only(self):
        """Max bound only."""
        assert clamp_float(15.0, hi=10.0) == 10.0
        assert clamp_float(5.0, hi=10.0) == 5.0

    def test_clamp_both_bounds(self):
        """Both bounds."""
        assert clamp_float(5.0, lo=0.0, hi=10.0) == 5.0
        assert clamp_float(-5.0, lo=0.0, hi=10.0) == 0.0
        assert clamp_float(15.0, lo=0.0, hi=10.0) == 10.0


# -----------------------------------------------------------------------------
# Test clamp_int
# -----------------------------------------------------------------------------

class TestClampInt:
    """Test clamp_int function."""

    def test_clamp_no_bounds(self):
        """No bounds should return original value."""
        assert clamp_int(100) == 100
        assert clamp_int(-100) == -100

    def test_clamp_min_only(self):
        """Min bound only."""
        assert clamp_int(5, lo=10) == 10
        assert clamp_int(15, lo=10) == 15

    def test_clamp_max_only(self):
        """Max bound only."""
        assert clamp_int(15, hi=10) == 10
        assert clamp_int(5, hi=10) == 5


# -----------------------------------------------------------------------------
# Test clamp_rgba
# -----------------------------------------------------------------------------

class TestClampRgba:
    """Test clamp_rgba function."""

    def test_valid_rgba(self):
        """Valid RGBA should be unchanged."""
        result = clamp_rgba([128, 64, 255, 200])
        assert result == [128, 64, 255, 200]

    def test_clamp_negative(self):
        """Negative values should clamp to 0."""
        result = clamp_rgba([-10, 128, 300, 255])
        assert result[0] == 0

    def test_clamp_over_255(self):
        """Values over 255 should clamp to 255."""
        result = clamp_rgba([128, 300, 128, 256])
        assert result[1] == 255
        assert result[3] == 255

    def test_short_list_padded(self):
        """Short list should be padded with 255."""
        result = clamp_rgba([100, 100, 100])
        assert len(result) == 4
        assert result[3] == 255

    def test_returns_new_list(self):
        """Should return new list, not mutate input."""
        original = [128, 128, 128, 128]
        result = clamp_rgba(original)
        result[0] = 0
        assert original[0] == 128


# -----------------------------------------------------------------------------
# Test wrap_deg
# -----------------------------------------------------------------------------

class TestWrapDeg:
    """Test wrap_deg function."""

    def test_value_in_range(self):
        """Value in [0, 360) should be unchanged."""
        assert wrap_deg(45.0) == 45.0
        assert wrap_deg(0.0) == 0.0
        assert wrap_deg(359.9) == 359.9

    def test_wrap_360(self):
        """360 should wrap to 0."""
        assert wrap_deg(360.0) == 0.0

    def test_wrap_over_360(self):
        """Values over 360 should wrap."""
        assert wrap_deg(450.0) == 90.0
        assert wrap_deg(720.0) == 0.0

    def test_wrap_negative(self):
        """Negative values should wrap."""
        result = wrap_deg(-45.0)
        assert result == 315.0

    def test_wrap_large_negative(self):
        """Large negative values should wrap."""
        result = wrap_deg(-720.0)
        assert result == 0.0


# -----------------------------------------------------------------------------
# Test apply_inspector_delta with Constraints
# -----------------------------------------------------------------------------

class TestApplyInspectorDeltaConstraints:
    """Test apply_inspector_delta applies proper constraints."""

    @pytest.fixture
    def light_entity(self) -> Dict[str, Any]:
        """Entity with light component."""
        return {
            "id": "light",
            "components": {
                "light": {
                    "radius_px": 160.0,
                    "flicker_amount": 0.5,
                    "flicker_speed": 1.0,
                    "cookie_scale": 1.0,
                    "cookie_rotation_deg": 0.0,
                    "flicker_enabled": False,
                }
            }
        }

    @pytest.fixture
    def transform_entity(self) -> Dict[str, Any]:
        """Entity with transform component."""
        return {
            "id": "trans",
            "components": {
                "transform": {"x": 100.0, "y": 100.0, "rot": 350.0}
            }
        }

    def test_radius_clamp_min_8(self, light_entity: Dict[str, Any]):
        """Radius should not go below 8."""
        # Try to reduce radius below minimum
        result = apply_inspector_delta(light_entity, "light", "radius_px", -200.0, shift=False)
        assert result["components"]["light"]["radius_px"] == 8.0

    def test_flicker_amount_clamp_0_1(self, light_entity: Dict[str, Any]):
        """Flicker amount should be in [0, 1]."""
        # Try to go below 0
        result = apply_inspector_delta(light_entity, "light", "flicker_amount", -1.0, shift=False)
        assert result["components"]["light"]["flicker_amount"] == 0.0

        # Try to go above 1
        result2 = apply_inspector_delta(light_entity, "light", "flicker_amount", 1.0, shift=False)
        assert result2["components"]["light"]["flicker_amount"] == 1.0

    def test_flicker_speed_clamp_min_0(self, light_entity: Dict[str, Any]):
        """Flicker speed should not go below 0."""
        result = apply_inspector_delta(light_entity, "light", "flicker_speed", -10.0, shift=False)
        assert result["components"]["light"]["flicker_speed"] == 0.0

    def test_cookie_scale_clamp_min_0(self, light_entity: Dict[str, Any]):
        """Cookie scale should not go below 0."""
        result = apply_inspector_delta(light_entity, "light", "cookie_scale", -10.0, shift=False)
        assert result["components"]["light"]["cookie_scale"] == 0.0

    def test_cookie_rotation_wraps(self, light_entity: Dict[str, Any]):
        """Cookie rotation should wrap in [0, 360)."""
        result = apply_inspector_delta(light_entity, "light", "cookie_rotation_deg", 400.0, shift=False)
        rot = result["components"]["light"]["cookie_rotation_deg"]
        assert 0.0 <= rot < 360.0

    def test_transform_x_y_free(self, transform_entity: Dict[str, Any]):
        """Transform x/y should be unconstrained."""
        result = apply_inspector_delta(transform_entity, "transform", "x", -500.0, shift=False)
        assert result["components"]["transform"]["x"] == -400.0

        result2 = apply_inspector_delta(transform_entity, "transform", "y", 10000.0, shift=False)
        assert result2["components"]["transform"]["y"] == 10100.0

    def test_transform_rot_wraps(self, transform_entity: Dict[str, Any]):
        """Transform rotation should wrap in [0, 360)."""
        result = apply_inspector_delta(transform_entity, "transform", "rot", 20.0, shift=False)
        rot = result["components"]["transform"]["rot"]
        assert rot == 10.0  # 350 + 20 = 370 -> wraps to 10

    def test_bool_field_toggles(self, light_entity: Dict[str, Any]):
        """Bool fields should toggle."""
        assert light_entity["components"]["light"]["flicker_enabled"] is False
        result = apply_inspector_delta(light_entity, "light", "flicker_enabled", 1.0, shift=False)
        assert result["components"]["light"]["flicker_enabled"] is True

        result2 = apply_inspector_delta(result, "light", "flicker_enabled", 1.0, shift=False)
        assert result2["components"]["light"]["flicker_enabled"] is False

    def test_shift_multiplier(self, transform_entity: Dict[str, Any]):
        """Shift should apply 10x multiplier."""
        # Normal delta of 1.0
        result = apply_inspector_delta(transform_entity, "transform", "x", 1.0, shift=False)
        assert result["components"]["transform"]["x"] == 101.0

        # Shift delta of 1.0 should be 10.0
        result2 = apply_inspector_delta(transform_entity, "transform", "x", 1.0, shift=True)
        assert result2["components"]["transform"]["x"] == 110.0

    def test_enum_field_cycles(self):
        """Enum fields should cycle through options."""
        entity = {"id": "e", "components": {"collider": {"kind": "none"}}}

        # Cycle forward
        result = apply_inspector_delta(entity, "collider", "kind", 1.0, shift=False)
        assert result["components"]["collider"]["kind"] == "rect"

        # Cycle forward again
        result2 = apply_inspector_delta(result, "collider", "kind", 1.0, shift=False)
        assert result2["components"]["collider"]["kind"] == "circle"

        # Cycle forward wraps
        result3 = apply_inspector_delta(result2, "collider", "kind", 1.0, shift=False)
        assert result3["components"]["collider"]["kind"] == "none"

    def test_enum_field_cycles_backward(self):
        """Enum fields should cycle backward with negative delta."""
        entity = {"id": "e", "components": {"collider": {"kind": "rect"}}}

        result = apply_inspector_delta(entity, "collider", "kind", -1.0, shift=False)
        assert result["components"]["collider"]["kind"] == "none"


# -----------------------------------------------------------------------------
# Test reset_field_to_default
# -----------------------------------------------------------------------------

class TestResetFieldToDefault:
    """Test reset_field_to_default function."""

    def test_reset_light_radius(self):
        """Reset light radius to default."""
        entity = {"id": "e", "components": {"light": {"radius_px": 500.0}}}
        result = reset_field_to_default(entity, "light", "radius_px")
        assert result["components"]["light"]["radius_px"] == LIGHT_DEFAULTS["radius_px"]

    def test_reset_transform_x(self):
        """Reset transform x to default."""
        entity = {"id": "e", "components": {"transform": {"x": 999.0}}}
        result = reset_field_to_default(entity, "transform", "x")
        assert result["components"]["transform"]["x"] == TRANSFORM_DEFAULTS["x"]

    def test_reset_unknown_field_unchanged(self):
        """Resetting unknown field should return unchanged."""
        entity = {"id": "e", "components": {"transform": {"x": 999.0}}}
        result = reset_field_to_default(entity, "transform", "unknown_field")
        assert result["components"]["transform"]["x"] == 999.0


# -----------------------------------------------------------------------------
# Test get_step_for_field
# -----------------------------------------------------------------------------

class TestGetStepForField:
    """Test get_step_for_field function."""

    def test_transform_steps(self):
        """Transform fields should have expected steps."""
        assert get_step_for_field("transform", "x") == 1.0
        assert get_step_for_field("transform", "y") == 1.0
        assert get_step_for_field("transform", "rot") == 5.0

    def test_light_steps(self):
        """Light fields should have expected steps."""
        assert get_step_for_field("light", "radius_px") == 4.0
        assert get_step_for_field("light", "flicker_amount") == 0.05
        assert get_step_for_field("light", "flicker_speed") == 0.25

    def test_unknown_field_defaults_to_1(self):
        """Unknown fields should default to step of 1.0."""
        assert get_step_for_field("transform", "unknown") == 1.0


# -----------------------------------------------------------------------------
# Test cycle_enum_value
# -----------------------------------------------------------------------------

class TestCycleEnumValue:
    """Test cycle_enum_value function."""

    def test_cycle_forward(self):
        """Cycle forward through options."""
        options = ("a", "b", "c")
        assert cycle_enum_value("a", options, 1) == "b"
        assert cycle_enum_value("b", options, 1) == "c"
        assert cycle_enum_value("c", options, 1) == "a"  # Wraps

    def test_cycle_backward(self):
        """Cycle backward through options."""
        options = ("a", "b", "c")
        assert cycle_enum_value("a", options, -1) == "c"  # Wraps
        assert cycle_enum_value("b", options, -1) == "a"
        assert cycle_enum_value("c", options, -1) == "b"

    def test_unknown_value_starts_at_0(self):
        """Unknown current value should start at first option."""
        options = ("a", "b", "c")
        assert cycle_enum_value("unknown", options, 1) == "b"
