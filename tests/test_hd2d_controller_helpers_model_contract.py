"""Contract tests for engine/editor/hd2d_controller_helpers_model.py.

Tests the thin wrapper functions for HD-2D controller operations:
- Clipboard patch extraction and validation
- Batch radius computation
- Display formatting
"""

from __future__ import annotations

import pytest

from engine.editor.hd2d_controller_helpers_model import (
    compute_clipboard_patch_from_entity,
    compute_next_batch_radius,
    count_clipboard_patch_fields,
    format_batch_radius_display,
    get_batch_radius_default,
    validate_clipboard_patch,
)


# =============================================================================
# Test compute_clipboard_patch_from_entity
# =============================================================================


class TestComputeClipboardPatchFromEntity:
    """Tests for compute_clipboard_patch_from_entity function."""

    def test_extracts_override_fields(self) -> None:
        """Should extract HD-2D override fields from entity dict."""
        entity = {
            "id": "player_1",
            "shadow_enabled": True,
            "outline_enabled": False,
            "depth_tint_strength": 0.5,
            "x": 100,  # Not an override field
            "y": 200,  # Not an override field
        }
        patch = compute_clipboard_patch_from_entity(entity)

        assert "shadow_enabled" in patch
        assert "outline_enabled" in patch
        assert "depth_tint_strength" in patch
        assert "x" not in patch
        assert "y" not in patch

    def test_excludes_none_values(self) -> None:
        """Should exclude None values from patch."""
        entity = {
            "id": "player_1",
            "shadow_enabled": True,
            "outline_enabled": None,
        }
        patch = compute_clipboard_patch_from_entity(entity)

        assert "shadow_enabled" in patch
        assert "outline_enabled" not in patch

    def test_returns_empty_dict_for_no_overrides(self) -> None:
        """Should return empty dict when no overrides present."""
        entity = {"id": "player_1", "x": 100, "y": 200}
        patch = compute_clipboard_patch_from_entity(entity)
        assert patch == {}

    def test_handles_non_dict_gracefully(self) -> None:
        """Should handle non-dict input gracefully."""
        patch = compute_clipboard_patch_from_entity(None)  # type: ignore[arg-type]
        assert patch == {}


# =============================================================================
# Test compute_next_batch_radius
# =============================================================================


class TestComputeNextBatchRadius:
    """Tests for compute_next_batch_radius function."""

    def test_positive_delta_increases_radius(self) -> None:
        """Should increase radius for positive delta."""
        assert compute_next_batch_radius(96, 16) == 112

    def test_negative_delta_decreases_radius(self) -> None:
        """Should decrease radius for negative delta."""
        assert compute_next_batch_radius(96, -16) == 80

    def test_clamps_at_minimum(self) -> None:
        """Should clamp at minimum bound (16)."""
        assert compute_next_batch_radius(32, -32) == 16
        assert compute_next_batch_radius(16, -16) == 16

    def test_clamps_at_maximum(self) -> None:
        """Should clamp at maximum bound (512)."""
        assert compute_next_batch_radius(500, 32) == 512
        assert compute_next_batch_radius(512, 16) == 512

    def test_zero_delta_unchanged(self) -> None:
        """Should leave radius unchanged for zero delta."""
        assert compute_next_batch_radius(96, 0) == 96

    def test_is_deterministic(self) -> None:
        """Should produce deterministic results."""
        for _ in range(10):
            assert compute_next_batch_radius(96, 16) == 112


# =============================================================================
# Test get_batch_radius_default
# =============================================================================


class TestGetBatchRadiusDefault:
    """Tests for get_batch_radius_default function."""

    def test_returns_96(self) -> None:
        """Should return 96 as default batch radius."""
        assert get_batch_radius_default() == 96


# =============================================================================
# Test count_clipboard_patch_fields
# =============================================================================


class TestCountClipboardPatchFields:
    """Tests for count_clipboard_patch_fields function."""

    def test_counts_non_none_fields(self) -> None:
        """Should count non-None fields in patch."""
        patch = {"shadow_enabled": True, "outline_enabled": False, "depth_tint_strength": 0.5}
        assert count_clipboard_patch_fields(patch) == 3

    def test_excludes_none_values(self) -> None:
        """Should not count None values."""
        patch = {"shadow_enabled": True, "outline_enabled": None}
        assert count_clipboard_patch_fields(patch) == 1

    def test_returns_zero_for_empty_patch(self) -> None:
        """Should return 0 for empty patch."""
        assert count_clipboard_patch_fields({}) == 0

    def test_handles_non_dict_gracefully(self) -> None:
        """Should handle non-dict input gracefully."""
        assert count_clipboard_patch_fields(None) == 0  # type: ignore[arg-type]


# =============================================================================
# Test format_batch_radius_display
# =============================================================================


class TestFormatBatchRadiusDisplay:
    """Tests for format_batch_radius_display function."""

    def test_formats_default_radius(self) -> None:
        """Should format default radius correctly."""
        assert format_batch_radius_display(96) == "Batch: 96px"

    def test_formats_various_values(self) -> None:
        """Should format various values correctly."""
        assert format_batch_radius_display(16) == "Batch: 16px"
        assert format_batch_radius_display(128) == "Batch: 128px"
        assert format_batch_radius_display(512) == "Batch: 512px"


# =============================================================================
# Test validate_clipboard_patch
# =============================================================================


class TestValidateClipboardPatch:
    """Tests for validate_clipboard_patch function."""

    def test_returns_true_for_valid_patch(self) -> None:
        """Should return True for non-empty dict."""
        assert validate_clipboard_patch({"key": "value"}) is True

    def test_returns_false_for_empty_dict(self) -> None:
        """Should return False for empty dict."""
        assert validate_clipboard_patch({}) is False

    def test_returns_false_for_none(self) -> None:
        """Should return False for None."""
        assert validate_clipboard_patch(None) is False

    def test_returns_false_for_non_dict(self) -> None:
        """Should return False for non-dict types."""
        assert validate_clipboard_patch("string") is False  # type: ignore[arg-type]
        assert validate_clipboard_patch([1, 2, 3]) is False  # type: ignore[arg-type]
        assert validate_clipboard_patch(123) is False  # type: ignore[arg-type]
