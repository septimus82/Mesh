"""Contract tests for selection outline style resolution.

Tests the pure style resolver for alt-drag duplicate highlighting.
Headless, deterministic - no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.selection_outline import (
    resolve_selection_styles,
    resolve_primary_for_alt_dup,
    STYLE_NORMAL,
    STYLE_ORIGINAL,
    STYLE_DUPLICATE,
)


# -----------------------------------------------------------------------------
# resolve_selection_styles
# -----------------------------------------------------------------------------


class TestResolveSelectionStyles:
    """Tests for resolve_selection_styles function."""

    def test_all_normal_when_alt_dup_inactive(self) -> None:
        """When alt-dup is inactive, all selected entities get 'normal' style."""
        result = resolve_selection_styles(
            selected_ids=["entity_a", "entity_b", "entity_c"],
            alt_dup_active=False,
            alt_dup_original_ids=None,
            alt_dup_duplicate_ids=None,
        )
        assert result == {
            "entity_a": STYLE_NORMAL,
            "entity_b": STYLE_NORMAL,
            "entity_c": STYLE_NORMAL,
        }

    def test_originals_tagged_original_when_active(self) -> None:
        """When alt-dup is active, original entities get 'original' style."""
        result = resolve_selection_styles(
            selected_ids=["entity_a_copy_1", "entity_b_copy_1"],
            alt_dup_active=True,
            alt_dup_original_ids=["entity_a", "entity_b"],
            alt_dup_duplicate_ids=["entity_a_copy_1", "entity_b_copy_1"],
        )
        # Originals should be included even if not in selected_ids
        assert result["entity_a"] == STYLE_ORIGINAL
        assert result["entity_b"] == STYLE_ORIGINAL

    def test_duplicates_tagged_duplicate_when_active(self) -> None:
        """When alt-dup is active, duplicate entities get 'duplicate' style."""
        result = resolve_selection_styles(
            selected_ids=["entity_a_copy_1", "entity_b_copy_1"],
            alt_dup_active=True,
            alt_dup_original_ids=["entity_a", "entity_b"],
            alt_dup_duplicate_ids=["entity_a_copy_1", "entity_b_copy_1"],
        )
        assert result["entity_a_copy_1"] == STYLE_DUPLICATE
        assert result["entity_b_copy_1"] == STYLE_DUPLICATE

    def test_mixed_selection_during_alt_dup(self) -> None:
        """Mixed selection during alt-dup: originals, duplicates, and others."""
        result = resolve_selection_styles(
            selected_ids=["entity_a_copy_1", "entity_c"],  # copy + unrelated
            alt_dup_active=True,
            alt_dup_original_ids=["entity_a"],
            alt_dup_duplicate_ids=["entity_a_copy_1"],
        )
        # Duplicate
        assert result["entity_a_copy_1"] == STYLE_DUPLICATE
        # Original (added even though not in selected_ids)
        assert result["entity_a"] == STYLE_ORIGINAL
        # Unrelated entity
        assert result["entity_c"] == STYLE_NORMAL

    def test_deterministic_ordering(self) -> None:
        """Style map keys should be sorted for determinism."""
        result = resolve_selection_styles(
            selected_ids=["z_entity", "a_entity", "m_entity"],
            alt_dup_active=False,
            alt_dup_original_ids=None,
            alt_dup_duplicate_ids=None,
        )
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_empty_selection(self) -> None:
        """Empty selection returns empty style map."""
        result = resolve_selection_styles(
            selected_ids=[],
            alt_dup_active=False,
            alt_dup_original_ids=None,
            alt_dup_duplicate_ids=None,
        )
        assert result == {}

    def test_stability_same_input_same_output(self) -> None:
        """Same inputs should produce identical outputs."""
        inputs = dict(
            selected_ids=["entity_a_copy_1", "entity_b_copy_1"],
            alt_dup_active=True,
            alt_dup_original_ids=["entity_a", "entity_b"],
            alt_dup_duplicate_ids=["entity_a_copy_1", "entity_b_copy_1"],
        )
        result1 = resolve_selection_styles(**inputs)
        result2 = resolve_selection_styles(**inputs)
        assert result1 == result2

    def test_originals_not_in_selection_still_included(self) -> None:
        """Original IDs not in selected_ids should still appear with 'original' style."""
        result = resolve_selection_styles(
            selected_ids=["entity_a_copy_1"],  # Only duplicate selected
            alt_dup_active=True,
            alt_dup_original_ids=["entity_a"],
            alt_dup_duplicate_ids=["entity_a_copy_1"],
        )
        assert "entity_a" in result
        assert result["entity_a"] == STYLE_ORIGINAL

    def test_none_lists_handled_gracefully(self) -> None:
        """None values for original/duplicate lists should be handled."""
        result = resolve_selection_styles(
            selected_ids=["entity_a"],
            alt_dup_active=True,
            alt_dup_original_ids=None,
            alt_dup_duplicate_ids=None,
        )
        # With no originals/duplicates info, entity gets normal style
        assert result["entity_a"] == STYLE_NORMAL


# -----------------------------------------------------------------------------
# resolve_primary_for_alt_dup
# -----------------------------------------------------------------------------


class TestResolvePrimaryForAltDup:
    """Tests for resolve_primary_for_alt_dup function."""

    def test_returns_current_when_alt_dup_inactive(self) -> None:
        """When alt-dup inactive, returns current primary."""
        result = resolve_primary_for_alt_dup(
            current_primary_id="entity_a",
            alt_dup_active=False,
            alt_dup_pivot_new_id="entity_a_copy_1",
        )
        assert result == "entity_a"

    def test_returns_pivot_when_alt_dup_active(self) -> None:
        """When alt-dup active, returns pivot duplicate ID."""
        result = resolve_primary_for_alt_dup(
            current_primary_id="entity_a_copy_1",
            alt_dup_active=True,
            alt_dup_pivot_new_id="entity_a_copy_1",
        )
        assert result == "entity_a_copy_1"

    def test_returns_current_when_pivot_none(self) -> None:
        """When alt-dup active but pivot is None, returns current."""
        result = resolve_primary_for_alt_dup(
            current_primary_id="entity_a",
            alt_dup_active=True,
            alt_dup_pivot_new_id=None,
        )
        assert result == "entity_a"

    def test_returns_none_when_all_none(self) -> None:
        """When all inputs are None/False, returns None."""
        result = resolve_primary_for_alt_dup(
            current_primary_id=None,
            alt_dup_active=False,
            alt_dup_pivot_new_id=None,
        )
        assert result is None
