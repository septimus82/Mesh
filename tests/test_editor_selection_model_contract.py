"""Contract tests for engine/editor/editor_selection_model.py.

Tests the pure functions for extracting selection information:
- Getting selected entity ID
- Checking selection state
- Building selection summaries
"""

from __future__ import annotations

from typing import Any

from engine.editor.editor_selection_model import (
    is_entity_selected,
    is_multi_selected,
    is_scene_selected,
    selected_entity_id,
    selected_entity_ids,
    selection_count,
    selection_summary,
)
from tests._typing import as_any

# =============================================================================
# Test Fixtures
# =============================================================================


class MockState:
    """Mock state object for testing selection functions."""

    def __init__(
        self,
        primary_entity_id: str | None = None,
        selected_entity: Any = None,
        selected_entity_ids: list[str] | None = None,
    ):
        self._primary_entity_id = primary_entity_id
        self.selected_entity = selected_entity
        self._selected_entity_ids = selected_entity_ids if selected_entity_ids is not None else []


class MockSprite:
    """Mock sprite with mesh_name and mesh_entity_data."""

    def __init__(self, mesh_name: str | None = None, entity_data: dict | None = None):
        self.mesh_name = mesh_name
        self.mesh_entity_data = entity_data if entity_data is not None else {}


# =============================================================================
# Test selected_entity_id
# =============================================================================


class TestSelectedEntityId:
    """Tests for selected_entity_id function."""

    def test_returns_primary_entity_id_when_set(self) -> None:
        """Should return _primary_entity_id when available."""
        state = MockState(primary_entity_id="entity_123")
        assert selected_entity_id(state) == "entity_123"

    def test_falls_back_to_sprite_mesh_name(self) -> None:
        """Should fall back to selected_entity.mesh_name."""
        sprite = MockSprite(mesh_name="player_1")
        state = MockState(selected_entity=sprite)
        assert selected_entity_id(state) == "player_1"

    def test_falls_back_to_sprite_entity_data_id(self) -> None:
        """Should fall back to mesh_entity_data['id']."""
        sprite = MockSprite(entity_data={"id": "npc_42"})
        state = MockState(selected_entity=sprite)
        assert selected_entity_id(state) == "npc_42"

    def test_returns_none_when_no_selection(self) -> None:
        """Should return None when nothing selected."""
        state = MockState()
        assert selected_entity_id(state) is None

    def test_prefers_primary_id_over_sprite(self) -> None:
        """Should prefer _primary_entity_id over sprite attributes."""
        sprite = MockSprite(mesh_name="sprite_name")
        state = MockState(primary_entity_id="primary_id", selected_entity=sprite)
        assert selected_entity_id(state) == "primary_id"

    def test_handles_missing_attributes_gracefully(self) -> None:
        """Should handle objects missing expected attributes."""
        state = object()  # No selection attributes
        assert selected_entity_id(state) is None


# =============================================================================
# Test is_entity_selected
# =============================================================================


class TestIsEntitySelected:
    """Tests for is_entity_selected function."""

    def test_returns_true_when_entity_selected(self) -> None:
        """Should return True when an entity is selected."""
        state = MockState(primary_entity_id="entity_123")
        assert is_entity_selected(state) is True

    def test_returns_false_when_no_selection(self) -> None:
        """Should return False when nothing selected."""
        state = MockState()
        assert is_entity_selected(state) is False

    def test_returns_true_for_sprite_selection(self) -> None:
        """Should return True when selected via sprite."""
        sprite = MockSprite(mesh_name="player_1")
        state = MockState(selected_entity=sprite)
        assert is_entity_selected(state) is True


# =============================================================================
# Test is_multi_selected
# =============================================================================


class TestIsMultiSelected:
    """Tests for is_multi_selected function."""

    def test_returns_true_for_multiple_selections(self) -> None:
        """Should return True when multiple entities selected."""
        state = MockState(selected_entity_ids=["entity_1", "entity_2"])
        assert is_multi_selected(state) is True

    def test_returns_false_for_single_selection(self) -> None:
        """Should return False for single selection."""
        state = MockState(selected_entity_ids=["entity_1"])
        assert is_multi_selected(state) is False

    def test_returns_false_for_empty_selection(self) -> None:
        """Should return False for empty selection list."""
        state = MockState(selected_entity_ids=[])
        assert is_multi_selected(state) is False

    def test_handles_missing_attribute(self) -> None:
        """Should handle missing _selected_entity_ids attribute."""
        state = object()
        assert is_multi_selected(state) is False


# =============================================================================
# Test selected_entity_ids
# =============================================================================


class TestSelectedEntityIds:
    """Tests for selected_entity_ids function."""

    def test_returns_list_of_ids(self) -> None:
        """Should return list of selected entity IDs."""
        state = MockState(selected_entity_ids=["entity_1", "entity_2"])
        assert selected_entity_ids(state) == ["entity_1", "entity_2"]

    def test_returns_copy_not_reference(self) -> None:
        """Should return a copy to prevent mutation."""
        original_ids = ["entity_1", "entity_2"]
        state = MockState(selected_entity_ids=original_ids)
        result = selected_entity_ids(state)
        result.append("entity_3")
        assert original_ids == ["entity_1", "entity_2"]

    def test_returns_empty_list_for_no_selection(self) -> None:
        """Should return empty list when nothing selected."""
        state = MockState()
        assert selected_entity_ids(state) == []


# =============================================================================
# Test selection_count
# =============================================================================


class TestSelectionCount:
    """Tests for selection_count function."""

    def test_returns_count_from_ids_list(self) -> None:
        """Should return count from _selected_entity_ids list."""
        state = MockState(selected_entity_ids=["a", "b", "c"])
        assert selection_count(state) == 3

    def test_returns_zero_for_empty_selection(self) -> None:
        """Should return 0 for empty selection."""
        state = MockState()
        assert selection_count(state) == 0

    def test_falls_back_to_single_selection_check(self) -> None:
        """Should check single selection if ids list not available."""
        state = MockState(primary_entity_id="entity_1")
        # Clear the list to force fallback
        as_any(state)._selected_entity_ids = None
        # Actually let's test with proper attribute removal
        delattr(state, "_selected_entity_ids")
        assert selection_count(state) == 1


# =============================================================================
# Test selection_summary
# =============================================================================


class TestSelectionSummary:
    """Tests for selection_summary function."""

    def test_returns_complete_summary(self) -> None:
        """Should return complete summary dict."""
        state = MockState(
            primary_entity_id="entity_1",
            selected_entity_ids=["entity_1", "entity_2"],
        )
        summary = selection_summary(state)

        assert summary["primary_id"] == "entity_1"
        assert summary["selected_ids"] == ["entity_1", "entity_2"]
        assert summary["count"] == 2
        assert summary["is_multi"] is True

    def test_returns_summary_for_single_selection(self) -> None:
        """Should return correct summary for single selection."""
        state = MockState(primary_entity_id="entity_1", selected_entity_ids=["entity_1"])
        summary = selection_summary(state)

        assert summary["primary_id"] == "entity_1"
        assert summary["count"] == 1
        assert summary["is_multi"] is False

    def test_returns_summary_for_no_selection(self) -> None:
        """Should return correct summary when nothing selected."""
        state = MockState()
        summary = selection_summary(state)

        assert summary["primary_id"] is None
        assert summary["selected_ids"] == []
        assert summary["count"] == 0
        assert summary["is_multi"] is False


# =============================================================================
# Test is_scene_selected
# =============================================================================


class TestIsSceneSelected:
    """Tests for is_scene_selected function."""

    def test_returns_true_when_no_entity_selected(self) -> None:
        """Should return True when no entity is selected."""
        state = MockState()
        assert is_scene_selected(state) is True

    def test_returns_false_when_entity_selected(self) -> None:
        """Should return False when an entity is selected."""
        state = MockState(primary_entity_id="entity_1")
        assert is_scene_selected(state) is False
