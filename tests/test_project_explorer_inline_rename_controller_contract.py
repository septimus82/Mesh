"""Contract tests for ProjectExplorerController inline rename methods.

These tests verify the controller state transitions for inline rename UX.
Tests cover:
- Begin/cancel/commit lifecycle
- Text input handling
- Backspace/delete key handling
- State queries (display text, original path)
- Selection change cancellation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_project_explorer_controller import ProjectExplorerController


@pytest.fixture
def controller() -> ProjectExplorerController:
    """Create a controller with a mock repo root."""
    return ProjectExplorerController(Path("/mock/repo"))


class TestInlineRenameActive:
    """Tests for inline_rename_active property."""

    def test_inactive_by_default(self, controller: ProjectExplorerController) -> None:
        """Inline rename is not active by default."""
        assert controller.inline_rename_active is False

    def test_active_after_begin(self, controller: ProjectExplorerController) -> None:
        """Inline rename is active after begin."""
        controller.begin_inline_rename("assets/hero.png")
        assert controller.inline_rename_active is True

    def test_inactive_after_cancel(self, controller: ProjectExplorerController) -> None:
        """Inline rename is not active after cancel."""
        controller.begin_inline_rename("assets/hero.png")
        controller.cancel_inline_rename()
        assert controller.inline_rename_active is False


class TestBeginInlineRename:
    """Tests for begin_inline_rename method."""

    def test_returns_true_for_valid_file(self, controller: ProjectExplorerController) -> None:
        """Returns True for valid file path."""
        result = controller.begin_inline_rename("assets/hero.png")
        assert result is True

    def test_returns_false_for_empty_path(self, controller: ProjectExplorerController) -> None:
        """Returns False for empty path."""
        result = controller.begin_inline_rename("")
        assert result is False

    def test_returns_false_for_directory(self, controller: ProjectExplorerController) -> None:
        """Returns False for directory path."""
        result = controller.begin_inline_rename("assets/")
        assert result is False

    def test_sets_state_correctly(self, controller: ProjectExplorerController) -> None:
        """Sets inline rename state with correct values."""
        controller.begin_inline_rename("assets/sprites/hero.png")
        
        state = controller.inline_rename_state
        assert state is not None
        assert state.original_path == "assets/sprites/hero.png"
        assert state.original_basename == "hero.png"
        assert state.original_stem == "hero"
        assert state.original_ext == ".png"
        assert state.current_text == "hero"

    def test_replaces_existing_rename_session(self, controller: ProjectExplorerController) -> None:
        """Starting new rename replaces existing session."""
        controller.begin_inline_rename("assets/hero.png")
        controller.begin_inline_rename("assets/villain.png")
        
        state = controller.inline_rename_state
        assert state is not None
        assert state.original_basename == "villain.png"


class TestCancelInlineRename:
    """Tests for cancel_inline_rename method."""

    def test_clears_state(self, controller: ProjectExplorerController) -> None:
        """Cancel clears the inline rename state."""
        controller.begin_inline_rename("assets/hero.png")
        controller.cancel_inline_rename()
        
        assert controller.inline_rename_state is None

    def test_noop_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Cancel is a no-op when not active."""
        controller.cancel_inline_rename()
        assert controller.inline_rename_state is None


class TestGetInlineRenameCommitResult:
    """Tests for get_inline_rename_commit_result method."""

    def test_returns_false_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Returns (False, None, None) when not in rename mode."""
        should_commit, new_name, error = controller.get_inline_rename_commit_result()
        assert should_commit is False
        assert new_name is None
        assert error is None

    def test_returns_true_with_valid_change(self, controller: ProjectExplorerController) -> None:
        """Returns True with new name when valid change."""
        controller.begin_inline_rename("assets/hero.png")
        controller.handle_rename_text_input("player")  # Types "player", replacing "hero"
        
        should_commit, new_name, error = controller.get_inline_rename_commit_result()
        assert should_commit is True
        assert new_name == "player.png"
        assert error is None

    def test_returns_false_with_no_change(self, controller: ProjectExplorerController) -> None:
        """Returns False with no error when name unchanged."""
        controller.begin_inline_rename("assets/hero.png")
        # Don't change anything
        
        should_commit, new_name, error = controller.get_inline_rename_commit_result()
        assert should_commit is False
        assert new_name is None
        assert error is None  # Not an error, just no change

    def test_returns_false_with_error_for_empty(self, controller: ProjectExplorerController) -> None:
        """Returns False with error when name empty."""
        controller.begin_inline_rename("assets/hero.png")
        # Delete all text
        for _ in range(4):  # "hero" is 4 chars
            controller.handle_rename_backspace()
        
        should_commit, new_name, error = controller.get_inline_rename_commit_result()
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"


class TestCommitInlineRename:
    """Tests for commit_inline_rename method."""

    def test_returns_success_and_new_name(self, controller: ProjectExplorerController) -> None:
        """Returns (True, new_name) on valid commit."""
        controller.begin_inline_rename("assets/hero.png")
        controller.handle_rename_text_input("player")
        
        success, new_name = controller.commit_inline_rename()
        assert success is True
        assert new_name == "player.png"

    def test_clears_state_on_success(self, controller: ProjectExplorerController) -> None:
        """Clears state after successful commit."""
        controller.begin_inline_rename("assets/hero.png")
        controller.handle_rename_text_input("player")
        controller.commit_inline_rename()
        
        assert controller.inline_rename_state is None

    def test_returns_false_on_no_change(self, controller: ProjectExplorerController) -> None:
        """Returns (False, None) when no change."""
        controller.begin_inline_rename("assets/hero.png")
        
        success, new_name = controller.commit_inline_rename()
        assert success is False
        assert new_name is None

    def test_clears_state_on_no_change(self, controller: ProjectExplorerController) -> None:
        """Clears state when no change (not an error)."""
        controller.begin_inline_rename("assets/hero.png")
        controller.commit_inline_rename()
        
        assert controller.inline_rename_state is None

    def test_keeps_state_on_error(self, controller: ProjectExplorerController) -> None:
        """Keeps state when there's an error (user can fix)."""
        controller.begin_inline_rename("assets/hero.png")
        # Make name empty
        for _ in range(4):
            controller.handle_rename_backspace()
        
        success, new_name = controller.commit_inline_rename()
        assert success is False
        # State should still be there so user can fix
        assert controller.inline_rename_state is not None


class TestHandleRenameTextInput:
    """Tests for handle_rename_text_input method."""

    def test_returns_false_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Returns False when not in rename mode."""
        result = controller.handle_rename_text_input("a")
        assert result is False

    def test_returns_true_and_appends_text(self, controller: ProjectExplorerController) -> None:
        """Returns True and appends text when in rename mode."""
        controller.begin_inline_rename("assets/hero.png")
        
        # First input replaces selection (entire stem is selected initially)
        result = controller.handle_rename_text_input("p")
        assert result is True
        assert controller.inline_rename_state is not None
        assert controller.inline_rename_state.current_text == "p"
        
        # Second input appends
        result = controller.handle_rename_text_input("l")
        assert result is True
        assert controller.inline_rename_state.current_text == "pl"

    def test_returns_false_for_non_printable(self, controller: ProjectExplorerController) -> None:
        """Returns False for non-printable characters."""
        controller.begin_inline_rename("assets/hero.png")
        
        result = controller.handle_rename_text_input("\x00")
        assert result is False

    def test_sanitizes_invalid_chars(self, controller: ProjectExplorerController) -> None:
        """Sanitizes invalid filename characters."""
        controller.begin_inline_rename("assets/hero.png")
        
        controller.handle_rename_text_input("file<name")
        assert controller.inline_rename_state is not None
        assert "<" not in controller.inline_rename_state.current_text


class TestHandleRenameBackspace:
    """Tests for handle_rename_backspace method."""

    def test_returns_false_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Returns False when not in rename mode."""
        result = controller.handle_rename_backspace()
        assert result is False

    def test_deletes_char_before_cursor(self, controller: ProjectExplorerController) -> None:
        """Deletes character before cursor."""
        controller.begin_inline_rename("assets/hero.png")
        # Type new text first to clear selection
        controller.handle_rename_text_input("test")
        
        controller.handle_rename_backspace()
        assert controller.inline_rename_state is not None
        assert controller.inline_rename_state.current_text == "tes"

    def test_returns_true_when_handled(self, controller: ProjectExplorerController) -> None:
        """Returns True when backspace is handled."""
        controller.begin_inline_rename("assets/hero.png")
        result = controller.handle_rename_backspace()
        assert result is True


class TestHandleRenameDelete:
    """Tests for handle_rename_delete method."""

    def test_returns_false_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Returns False when not in rename mode."""
        result = controller.handle_rename_delete()
        assert result is False

    def test_returns_true_when_handled(self, controller: ProjectExplorerController) -> None:
        """Returns True when delete is handled."""
        controller.begin_inline_rename("assets/hero.png")
        result = controller.handle_rename_delete()
        assert result is True


class TestGetRenameDisplayText:
    """Tests for get_rename_display_text method."""

    def test_returns_none_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Returns None when not in rename mode."""
        assert controller.get_rename_display_text() is None

    def test_returns_stem_plus_extension(self, controller: ProjectExplorerController) -> None:
        """Returns current text plus extension."""
        controller.begin_inline_rename("assets/hero.png")
        
        text = controller.get_rename_display_text()
        assert text == "hero.png"

    def test_reflects_edits(self, controller: ProjectExplorerController) -> None:
        """Reflects edits to the text."""
        controller.begin_inline_rename("assets/hero.png")
        controller.handle_rename_text_input("player")
        
        text = controller.get_rename_display_text()
        assert text == "player.png"


class TestGetRenameOriginalPath:
    """Tests for get_rename_original_path method."""

    def test_returns_none_when_not_active(self, controller: ProjectExplorerController) -> None:
        """Returns None when not in rename mode."""
        assert controller.get_rename_original_path() is None

    def test_returns_original_path(self, controller: ProjectExplorerController) -> None:
        """Returns the original path being renamed."""
        controller.begin_inline_rename("assets/sprites/hero.png")
        
        path = controller.get_rename_original_path()
        assert path == "assets/sprites/hero.png"


class TestIntegrationScenarios:
    """Integration tests for common rename scenarios."""

    def test_full_rename_workflow(self, controller: ProjectExplorerController) -> None:
        """Test a complete rename workflow."""
        # Start rename
        assert controller.begin_inline_rename("assets/hero.png") is True
        assert controller.inline_rename_active is True
        
        # Type new name (replaces selection)
        controller.handle_rename_text_input("player")
        assert controller.get_rename_display_text() == "player.png"
        
        # Commit
        success, new_name = controller.commit_inline_rename()
        assert success is True
        assert new_name == "player.png"
        assert controller.inline_rename_active is False

    def test_cancel_workflow(self, controller: ProjectExplorerController) -> None:
        """Test canceling a rename."""
        controller.begin_inline_rename("assets/hero.png")
        controller.handle_rename_text_input("player")
        
        controller.cancel_inline_rename()
        
        assert controller.inline_rename_active is False
        assert controller.get_rename_display_text() is None

    def test_dotfile_rename(self, controller: ProjectExplorerController) -> None:
        """Test renaming a dotfile."""
        controller.begin_inline_rename(".gitignore")
        
        assert controller.inline_rename_state is not None
        assert controller.inline_rename_state.original_stem == ".gitignore"
        assert controller.inline_rename_state.original_ext == ""
        
        controller.handle_rename_text_input(".dockerignore")
        
        success, new_name = controller.commit_inline_rename()
        assert success is True
        assert new_name == ".dockerignore"

    def test_preserve_extension(self, controller: ProjectExplorerController) -> None:
        """Test that extension is preserved during rename."""
        controller.begin_inline_rename("data/config.json")
        controller.handle_rename_text_input("settings")
        
        success, new_name = controller.commit_inline_rename()
        assert success is True
        assert new_name == "settings.json"

    def test_backspace_then_type(self, controller: ProjectExplorerController) -> None:
        """Test backspace then typing."""
        controller.begin_inline_rename("assets/hero.png")
        
        # First type replaces selection
        controller.handle_rename_text_input("test")
        assert controller.inline_rename_state is not None
        assert controller.inline_rename_state.current_text == "test"
        
        # Backspace twice
        controller.handle_rename_backspace()
        controller.handle_rename_backspace()
        assert controller.inline_rename_state.current_text == "te"
        
        # Type more
        controller.handle_rename_text_input("n")
        assert controller.inline_rename_state.current_text == "ten"
