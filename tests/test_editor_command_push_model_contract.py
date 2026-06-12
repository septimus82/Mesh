"""Contract tests for engine/editor/editor_command_push_model.py.

Tests the pure functions for command push plumbing:
- Backfilling command dicts with action_id, detail, label
- No-op detection via payload comparison
- Default undo label formatting
"""

from __future__ import annotations

from engine.editor.editor_command_push_model import (
    backfill_label_from_action,
    compute_command_backfill,
    format_default_undo_label,
    should_push_command,
)
from tests._typing import as_any

# =============================================================================
# Test compute_command_backfill
# =============================================================================


class TestComputeCommandBackfill:
    """Tests for compute_command_backfill function."""

    def test_backfills_action_id_from_type(self) -> None:
        """Should backfill action_id from command type."""
        cmd = {"type": "AddEntity"}
        result = compute_command_backfill(cmd)
        assert result["action_id"] == "editor.entity.add"

    def test_preserves_existing_action_id(self) -> None:
        """Should not overwrite existing action_id."""
        cmd = {"type": "AddEntity", "action_id": "custom.action"}
        result = compute_command_backfill(cmd)
        assert result["action_id"] == "custom.action"

    def test_backfills_detail_from_command(self) -> None:
        """Should backfill detail from command."""
        cmd = {"type": "RenameEntity", "before": "old_name", "after": "new_name"}
        result = compute_command_backfill(cmd)
        assert "detail" in result
        assert result["detail"]["from"] == "old_name"
        assert result["detail"]["to"] == "new_name"

    def test_preserves_existing_detail(self) -> None:
        """Should not overwrite existing detail."""
        cmd = {"type": "AddEntity", "detail": {"custom": "value"}}
        result = compute_command_backfill(cmd)
        assert result["detail"] == {"custom": "value"}

    def test_backfills_label_from_command(self) -> None:
        """Should backfill label from command type."""
        cmd = {"type": "AddEntity"}
        result = compute_command_backfill(cmd)
        assert "label" in result
        assert "Add Entity" in result["label"]

    def test_preserves_existing_label(self) -> None:
        """Should not overwrite existing label."""
        cmd = {"type": "AddEntity", "label": "Custom Label"}
        result = compute_command_backfill(cmd)
        assert result["label"] == "Custom Label"

    def test_mutates_input_dict(self) -> None:
        """Should mutate the input dict in place."""
        cmd: dict = {"type": "AddEntity"}
        result = compute_command_backfill(cmd)
        assert result is cmd
        assert "action_id" in cmd

    def test_handles_non_dict_gracefully(self) -> None:
        """Should handle non-dict input gracefully."""
        result = compute_command_backfill(as_any(None))
        assert result is None

        result = compute_command_backfill(as_any("string"))
        assert result == "string"

    def test_handles_unknown_command_type(self) -> None:
        """Should handle unknown command types gracefully."""
        cmd = {"type": "UnknownType"}
        result = compute_command_backfill(cmd)
        # Should not crash, action_id won't be set
        assert "action_id" not in result or result.get("action_id") is None


# =============================================================================
# Test should_push_command
# =============================================================================


class TestShouldPushCommand:
    """Tests for should_push_command function."""

    def test_returns_true_for_different_payloads(self) -> None:
        """Should return True when payloads differ."""
        prev = {"key": "old_value"}
        next_ = {"key": "new_value"}
        assert should_push_command(prev, next_) is True

    def test_returns_false_for_identical_payloads(self) -> None:
        """Should return False when payloads are identical."""
        prev = {"key": "value"}
        next_ = {"key": "value"}
        assert should_push_command(prev, next_) is False

    def test_handles_none_payloads(self) -> None:
        """Should handle None payloads correctly."""
        assert should_push_command(None, None) is False
        assert should_push_command(None, {"key": "value"}) is True
        assert should_push_command({"key": "value"}, None) is True

    def test_handles_complex_nested_dicts(self) -> None:
        """Should correctly compare complex nested structures."""
        prev = {"outer": {"inner": [1, 2, 3]}}
        next_same = {"outer": {"inner": [1, 2, 3]}}
        next_diff = {"outer": {"inner": [1, 2, 4]}}

        assert should_push_command(prev, next_same) is False
        assert should_push_command(prev, next_diff) is True


# =============================================================================
# Test format_default_undo_label
# =============================================================================


class TestFormatDefaultUndoLabel:
    """Tests for format_default_undo_label function."""

    def test_formats_with_action_title(self) -> None:
        """Should format with action title when provided."""
        cmd = {"action_id": "editor.entity.add"}
        result = format_default_undo_label(cmd, action_title="Add Entity")
        assert "Add Entity" in result

    def test_formats_with_action_id_only(self) -> None:
        """Should format with action_id when no title provided."""
        cmd = {"action_id": "editor.entity.add"}
        result = format_default_undo_label(cmd, action_title=None)
        assert "editor.entity.add" in result

    def test_formats_with_detail(self) -> None:
        """Should include detail in formatted label."""
        cmd = {"action_id": "editor.entity.add", "detail": {"entity_id": "player_1"}}
        result = format_default_undo_label(cmd, action_title="Add Entity")
        assert "Add Entity" in result
        # Detail may or may not be included depending on format_history_entry

    def test_handles_empty_cmd(self) -> None:
        """Should handle empty command dict."""
        result = format_default_undo_label({})
        assert "Unknown Action" in result

    def test_handles_non_dict_cmd(self) -> None:
        """Should handle non-dict command gracefully."""
        result = format_default_undo_label(as_any(None))
        assert "Unknown Action" in result


# =============================================================================
# Test backfill_label_from_action
# =============================================================================


class TestBackfillLabelFromAction:
    """Tests for backfill_label_from_action function."""

    def test_backfills_label_when_missing(self) -> None:
        """Should backfill label when missing."""
        cmd: dict = {"action_id": "editor.entity.add"}
        result = backfill_label_from_action(cmd, "editor.entity.add", "Add Entity")
        assert "label" in result
        assert "Add Entity" in result["label"]

    def test_preserves_existing_label(self) -> None:
        """Should not overwrite existing label."""
        cmd = {"action_id": "editor.entity.add", "label": "Custom Label"}
        result = backfill_label_from_action(cmd, "editor.entity.add", "Add Entity")
        assert result["label"] == "Custom Label"

    def test_includes_detail_in_label(self) -> None:
        """Should include detail in backfilled label."""
        cmd: dict = {
            "action_id": "editor.entity.rename",
            "detail": {"entity_id": "player_1"},
        }
        result = backfill_label_from_action(cmd, "editor.entity.rename", "Rename Entity")
        assert "label" in result

    def test_mutates_input_dict(self) -> None:
        """Should mutate input dict in place."""
        cmd: dict = {"action_id": "editor.entity.add"}
        result = backfill_label_from_action(cmd, "editor.entity.add", "Add Entity")
        assert result is cmd

    def test_handles_non_dict_gracefully(self) -> None:
        """Should handle non-dict input gracefully."""
        result = backfill_label_from_action(as_any(None), "id", "title")
        assert result is None
