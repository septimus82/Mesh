"""Contract tests for engine/editor/hd2d_batch_radius_model.py.

Tests the pure model functions for HD-2D batch radius:
- Clamping batch radius to valid bounds
- Nudging batch radius deterministically
- Formatting batch radius labels
"""

from __future__ import annotations

import pytest

from engine.editor.hd2d_batch_radius_model import (
    HD2D_BATCH_RADIUS_DEFAULT,
    HD2D_BATCH_RADIUS_MAX,
    HD2D_BATCH_RADIUS_MIN,
    HD2D_BATCH_RADIUS_STEP,
    clamp_batch_radius,
    format_batch_radius_label,
    nudge_batch_radius,
)
from tests._typing import as_any


# =============================================================================
# Test Constants
# =============================================================================


class TestBatchRadiusConstants:
    """Tests for batch radius constants."""

    def test_default_is_96(self) -> None:
        """Default radius should be 96."""
        assert HD2D_BATCH_RADIUS_DEFAULT == 96

    def test_min_is_16(self) -> None:
        """Minimum radius should be 16."""
        assert HD2D_BATCH_RADIUS_MIN == 16

    def test_max_is_512(self) -> None:
        """Maximum radius should be 512."""
        assert HD2D_BATCH_RADIUS_MAX == 512

    def test_step_is_16(self) -> None:
        """Step size should be 16."""
        assert HD2D_BATCH_RADIUS_STEP == 16

    def test_default_within_bounds(self) -> None:
        """Default should be within min/max bounds."""
        assert HD2D_BATCH_RADIUS_MIN <= HD2D_BATCH_RADIUS_DEFAULT <= HD2D_BATCH_RADIUS_MAX


# =============================================================================
# Test clamp_batch_radius
# =============================================================================


class TestClampBatchRadius:
    """Tests for clamp_batch_radius function."""

    def test_value_within_bounds_unchanged(self) -> None:
        """Value within bounds should be unchanged."""
        assert clamp_batch_radius(96) == 96
        assert clamp_batch_radius(100) == 100
        assert clamp_batch_radius(256) == 256

    def test_value_below_min_clamped(self) -> None:
        """Value below minimum should be clamped to minimum."""
        assert clamp_batch_radius(0) == HD2D_BATCH_RADIUS_MIN
        assert clamp_batch_radius(10) == HD2D_BATCH_RADIUS_MIN
        assert clamp_batch_radius(-100) == HD2D_BATCH_RADIUS_MIN

    def test_value_above_max_clamped(self) -> None:
        """Value above maximum should be clamped to maximum."""
        assert clamp_batch_radius(600) == HD2D_BATCH_RADIUS_MAX
        assert clamp_batch_radius(1000) == HD2D_BATCH_RADIUS_MAX

    def test_boundary_values(self) -> None:
        """Boundary values should be accepted."""
        assert clamp_batch_radius(HD2D_BATCH_RADIUS_MIN) == HD2D_BATCH_RADIUS_MIN
        assert clamp_batch_radius(HD2D_BATCH_RADIUS_MAX) == HD2D_BATCH_RADIUS_MAX

    def test_float_converted_to_int(self) -> None:
        """Float values should be converted to int."""
        assert clamp_batch_radius(96.5) == 96
        assert clamp_batch_radius(100.9) == 100

    def test_invalid_type_returns_default(self) -> None:
        """Invalid types should return default."""
        assert clamp_batch_radius(as_any(None)) == HD2D_BATCH_RADIUS_DEFAULT
        assert clamp_batch_radius(as_any("abc")) == HD2D_BATCH_RADIUS_DEFAULT
        assert clamp_batch_radius(as_any([])) == HD2D_BATCH_RADIUS_DEFAULT


# =============================================================================
# Test nudge_batch_radius
# =============================================================================


class TestNudgeBatchRadius:
    """Tests for nudge_batch_radius function."""

    def test_positive_nudge(self) -> None:
        """Positive delta should increase radius."""
        assert nudge_batch_radius(96, 16) == 112
        assert nudge_batch_radius(96, 32) == 128

    def test_negative_nudge(self) -> None:
        """Negative delta should decrease radius."""
        assert nudge_batch_radius(96, -16) == 80
        assert nudge_batch_radius(96, -32) == 64

    def test_nudge_clamps_at_min(self) -> None:
        """Nudging below minimum should clamp."""
        assert nudge_batch_radius(32, -32) == HD2D_BATCH_RADIUS_MIN
        assert nudge_batch_radius(16, -16) == HD2D_BATCH_RADIUS_MIN

    def test_nudge_clamps_at_max(self) -> None:
        """Nudging above maximum should clamp."""
        assert nudge_batch_radius(500, 32) == HD2D_BATCH_RADIUS_MAX
        assert nudge_batch_radius(512, 16) == HD2D_BATCH_RADIUS_MAX

    def test_zero_delta_unchanged(self) -> None:
        """Zero delta should leave value unchanged."""
        assert nudge_batch_radius(96, 0) == 96
        assert nudge_batch_radius(128, 0) == 128

    def test_nudge_is_deterministic(self) -> None:
        """Nudging should produce deterministic results."""
        # Same inputs should always produce same outputs
        for _ in range(10):
            assert nudge_batch_radius(96, 16) == 112
            assert nudge_batch_radius(112, -16) == 96

    def test_invalid_types_return_default(self) -> None:
        """Invalid types should return default."""
        assert nudge_batch_radius(as_any(None), 16) == HD2D_BATCH_RADIUS_DEFAULT
        assert nudge_batch_radius(96, as_any(None)) == HD2D_BATCH_RADIUS_DEFAULT
        assert nudge_batch_radius(as_any("abc"), 16) == HD2D_BATCH_RADIUS_DEFAULT


# =============================================================================
# Test format_batch_radius_label
# =============================================================================


class TestFormatBatchRadiusLabel:
    """Tests for format_batch_radius_label function."""

    def test_formats_default_radius(self) -> None:
        """Should format default radius correctly."""
        assert format_batch_radius_label(96) == "Batch: 96px"

    def test_formats_various_values(self) -> None:
        """Should format various values correctly."""
        assert format_batch_radius_label(16) == "Batch: 16px"
        assert format_batch_radius_label(128) == "Batch: 128px"
        assert format_batch_radius_label(512) == "Batch: 512px"

    def test_formats_float_as_int(self) -> None:
        """Should convert float to int for formatting."""
        assert format_batch_radius_label(96.5) == "Batch: 96px"
        assert format_batch_radius_label(100.9) == "Batch: 100px"

    def test_invalid_type_uses_default(self) -> None:
        """Invalid types should use default value."""
        assert format_batch_radius_label(as_any(None)) == f"Batch: {HD2D_BATCH_RADIUS_DEFAULT}px"
        assert format_batch_radius_label(as_any("abc")) == f"Batch: {HD2D_BATCH_RADIUS_DEFAULT}px"


# =============================================================================
# Test Workspace Settings Integration
# =============================================================================


class TestWorkspaceSettingsIntegration:
    """Tests for workspace settings integration with batch radius."""

    def test_workspace_settings_has_batch_radius_field(self) -> None:
        """WorkspaceSettings should have hd2d_batch_radius_px field."""
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings()
        assert hasattr(settings, "hd2d_batch_radius_px")
        assert settings.hd2d_batch_radius_px == 96

    def test_workspace_settings_from_dict_parses_radius(self) -> None:
        """from_dict should parse batch radius correctly."""
        from engine.workspace_settings import WorkspaceSettings

        data = {"hd2d_batch_radius_px": 128}
        settings = WorkspaceSettings.from_dict(data)
        assert settings.hd2d_batch_radius_px == 128

    def test_workspace_settings_from_dict_clamps_radius(self) -> None:
        """from_dict should clamp invalid radius values."""
        from engine.workspace_settings import WorkspaceSettings

        # Below minimum
        settings = WorkspaceSettings.from_dict({"hd2d_batch_radius_px": 5})
        assert settings.hd2d_batch_radius_px == HD2D_BATCH_RADIUS_MIN

        # Above maximum
        settings = WorkspaceSettings.from_dict({"hd2d_batch_radius_px": 1000})
        assert settings.hd2d_batch_radius_px == HD2D_BATCH_RADIUS_MAX

    def test_workspace_settings_from_dict_handles_missing(self) -> None:
        """from_dict should use default when field missing."""
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings.from_dict({})
        assert settings.hd2d_batch_radius_px == 96

    def test_workspace_settings_from_dict_handles_invalid_type(self) -> None:
        """from_dict should use default for invalid types."""
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings.from_dict({"hd2d_batch_radius_px": "invalid"})
        assert settings.hd2d_batch_radius_px == 96
