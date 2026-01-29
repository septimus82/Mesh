"""Contract tests for project_explorer_inline_rename_model.

These tests verify the pure model functions for inline rename UX.
Tests cover:
- Path renamability checks
- Basename/extension splitting (dotfiles, multi-dot, etc.)
- Initial rename text computation
- Input sanitization
- Commit validity checking
- State management functions
"""

from __future__ import annotations

import pytest

from engine.editor.project_explorer_inline_rename_model import (
    is_renameable_path,
    split_basename_ext,
    compute_initial_rename_text,
    compute_rename_selection,
    sanitize_rename_input,
    should_commit_rename,
    apply_extension_preservation,
    build_new_path,
    create_inline_rename_state,
    update_rename_text,
    append_rename_text,
    handle_rename_backspace,
    handle_rename_delete,
    get_final_rename_name,
    get_final_rename_path,
    move_cursor_left,
    move_cursor_right,
    move_cursor_home,
    move_cursor_end,
    is_word_char,
    find_prev_word_boundary,
    find_next_word_boundary,
    move_cursor_word_left,
    move_cursor_word_right,
    delete_prev_word,
    delete_next_word,
    normalize_committed_filename,
    is_reserved_filename,
    contains_path_separators,
    InlineRenameState,
    INVALID_FILENAME_CHARS,
)


class TestIsRenameablePath:
    """Tests for is_renameable_path function."""

    def test_empty_path_not_renameable(self) -> None:
        """Empty path cannot be renamed."""
        assert is_renameable_path("") is False
        assert is_renameable_path("   ") is False

    def test_regular_file_is_renameable(self) -> None:
        """Regular files can be renamed."""
        assert is_renameable_path("assets/sprites/hero.png") is True
        assert is_renameable_path("file.txt") is True
        assert is_renameable_path("scenes/level1.json") is True

    def test_directory_not_renameable(self) -> None:
        """Directories (ending in /) cannot be renamed."""
        assert is_renameable_path("assets/") is False
        assert is_renameable_path("folder/subfolder/") is False

    def test_dotfile_is_renameable(self) -> None:
        """Dotfiles can be renamed."""
        assert is_renameable_path(".gitignore") is True
        assert is_renameable_path("config/.env") is True

    def test_backslash_normalized(self) -> None:
        """Backslash paths are normalized and treated as files."""
        assert is_renameable_path("assets\\sprites\\hero.png") is True


class TestSplitBasenameExt:
    """Tests for split_basename_ext function."""

    def test_simple_file(self) -> None:
        """Simple filename with extension."""
        assert split_basename_ext("hero.png") == ("hero", ".png")
        assert split_basename_ext("scene.json") == ("scene", ".json")

    def test_no_extension(self) -> None:
        """Filename without extension."""
        assert split_basename_ext("README") == ("README", "")
        assert split_basename_ext("Makefile") == ("Makefile", "")

    def test_dotfile_no_extension(self) -> None:
        """Dotfile with no additional extension."""
        assert split_basename_ext(".gitignore") == (".gitignore", "")
        assert split_basename_ext(".env") == (".env", "")

    def test_dotfile_with_extension(self) -> None:
        """Dotfile with additional extension."""
        assert split_basename_ext(".env.local") == (".env", ".local")
        assert split_basename_ext(".config.json") == (".config", ".json")

    def test_multi_dot_filename(self) -> None:
        """Filename with multiple dots (uses last dot)."""
        # Note: We split on last dot, so "file.tar.gz" -> ("file.tar", ".gz")
        assert split_basename_ext("file.tar.gz") == ("file.tar", ".gz")
        assert split_basename_ext("backup.2024.01.15.json") == ("backup.2024.01.15", ".json")

    def test_empty_filename(self) -> None:
        """Empty filename."""
        assert split_basename_ext("") == ("", "")


class TestComputeInitialRenameText:
    """Tests for compute_initial_rename_text function."""

    def test_regular_file(self) -> None:
        """Regular file path."""
        stem, ext, basename = compute_initial_rename_text("assets/sprites/hero.png")
        assert stem == "hero"
        assert ext == ".png"
        assert basename == "hero.png"

    def test_file_at_root(self) -> None:
        """File at root level (no directory)."""
        stem, ext, basename = compute_initial_rename_text("config.json")
        assert stem == "config"
        assert ext == ".json"
        assert basename == "config.json"

    def test_dotfile(self) -> None:
        """Dotfile in directory."""
        stem, ext, basename = compute_initial_rename_text("project/.gitignore")
        assert stem == ".gitignore"
        assert ext == ""
        assert basename == ".gitignore"

    def test_dotfile_with_extension(self) -> None:
        """Dotfile with extension."""
        stem, ext, basename = compute_initial_rename_text(".env.local")
        assert stem == ".env"
        assert ext == ".local"
        assert basename == ".env.local"

    def test_empty_path(self) -> None:
        """Empty path returns empty values."""
        assert compute_initial_rename_text("") == ("", "", "")


class TestComputeRenameSelection:
    """Tests for compute_rename_selection function."""

    def test_selects_entire_stem(self) -> None:
        """Selection covers entire stem."""
        assert compute_rename_selection("hero") == (0, 4)
        assert compute_rename_selection("filename") == (0, 8)

    def test_empty_stem(self) -> None:
        """Empty stem gives empty selection."""
        assert compute_rename_selection("") == (0, 0)


class TestSanitizeRenameInput:
    """Tests for sanitize_rename_input function."""

    def test_valid_input_unchanged(self) -> None:
        """Valid input passes through unchanged."""
        assert sanitize_rename_input("hero") == "hero"
        assert sanitize_rename_input("my_file-2024") == "my_file-2024"

    def test_removes_invalid_chars(self) -> None:
        """Invalid characters are removed."""
        assert sanitize_rename_input("file<name>") == "filename"
        assert sanitize_rename_input('file:name') == "filename"
        assert sanitize_rename_input("file|name") == "filename"
        assert sanitize_rename_input("file?name") == "filename"
        assert sanitize_rename_input("file*name") == "filename"

    def test_removes_path_separators(self) -> None:
        """Path separators are removed."""
        assert sanitize_rename_input("file/name") == "filename"
        assert sanitize_rename_input("file\\name") == "filename"

    def test_removes_quotes(self) -> None:
        """Quotes are removed."""
        assert sanitize_rename_input('file"name') == "filename"

    def test_empty_input(self) -> None:
        """Empty input returns empty."""
        assert sanitize_rename_input("") == ""

    def test_removes_control_chars(self) -> None:
        """Control characters are removed."""
        assert sanitize_rename_input("file\x00name") == "filename"
        assert sanitize_rename_input("file\tname") == "filename"


class TestShouldCommitRename:
    """Tests for should_commit_rename function."""

    def test_valid_rename(self) -> None:
        """Valid rename with change should commit."""
        should_commit, new_name, error = should_commit_rename("hero", "player", ".png")
        assert should_commit is True
        assert new_name == "player.png"
        assert error is None

    def test_empty_not_allowed(self) -> None:
        """Empty stem not allowed."""
        should_commit, new_name, error = should_commit_rename("hero", "", ".png")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_whitespace_only_not_allowed(self) -> None:
        """Whitespace-only stem not allowed."""
        should_commit, new_name, error = should_commit_rename("hero", "   ", ".png")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_no_change_no_commit(self) -> None:
        """Same name should not commit (but no error)."""
        should_commit, new_name, error = should_commit_rename("hero", "hero", ".png")
        assert should_commit is False
        assert new_name is None
        assert error is None  # No error, just no change

    def test_invalid_char_error(self) -> None:
        """Invalid characters are sanitized and commit can succeed."""
        should_commit, new_name, error = should_commit_rename("hero", "player<bad>", ".png")
        assert should_commit is True
        assert new_name == "playerbad.png"
        assert error is None


class TestCommitNormalization:
    """Tests for commit normalization and reserved names."""

    def test_normalize_trailing_spaces(self) -> None:
        assert normalize_committed_filename("New Name   ") == "New Name"

    def test_normalize_trailing_dots(self) -> None:
        assert normalize_committed_filename("New Name...") == "New Name"

    def test_normalize_trailing_dots_and_spaces(self) -> None:
        assert normalize_committed_filename("New.  .") == "New"

    def test_reserved_names(self) -> None:
        assert is_reserved_filename("") is True
        assert is_reserved_filename(".") is True
        assert is_reserved_filename("..") is True
        assert is_reserved_filename("ok") is False

    def test_commit_rejects_whitespace_only(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "   ", ".png")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_dotfile_preserved(self) -> None:
        should_commit, new_name, error = should_commit_rename(".gitignore", ".gitignore", "")
        assert should_commit is False
        assert new_name is None
        assert error is None

        should_commit, new_name, error = should_commit_rename(".gitignore", ".gitignore ", "")
        assert should_commit is False
        assert new_name is None
        assert error is None

        should_commit, new_name, error = should_commit_rename(".gitignore", ".gitignore", "")
        assert should_commit is False
        assert new_name is None
        assert error is None

    def test_dotfile_rejects_dot(self) -> None:
        should_commit, new_name, error = should_commit_rename(".gitignore", ". ", "")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_extension_preservation_trailing_dot(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "hero.", ".png")
        assert should_commit is False
        assert new_name is None
        assert error is None

    def test_extension_preservation_empty_stem(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "", ".png")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_determinism_normalized_output(self) -> None:
        should_commit1, new_name1, error1 = should_commit_rename("hero", "New Name...", ".png")
        should_commit2, new_name2, error2 = should_commit_rename("hero", "New Name...", ".png")
        assert (should_commit1, new_name1, error1) == (should_commit2, new_name2, error2)


class TestSeparatorRejection:
    """Tests for rejecting path separators and drive-ish characters."""

    def test_contains_path_separators(self) -> None:
        assert contains_path_separators("foo/bar") is True
        assert contains_path_separators("foo\\bar") is True
        assert contains_path_separators("C:foo") is True
        assert contains_path_separators("foo:bar") is True
        assert contains_path_separators("foo-bar") is False

    def test_rejects_slash(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "foo/bar", "")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_rejects_backslash(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "foo\\bar", "")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_rejects_colon(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "C:foo", "")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

        should_commit, new_name, error = should_commit_rename("hero", "foo:bar", "")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

    def test_allows_dash(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "foo-bar", "")
        assert should_commit is True
        assert new_name == "foo-bar"
        assert error is None

    def test_extension_preservation_with_separators(self) -> None:
        should_commit, new_name, error = should_commit_rename("hero", "foo/bar", ".png")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

        should_commit, new_name, error = should_commit_rename("hero", "foo:bar", ".png")
        assert should_commit is False
        assert new_name is None
        assert error == "Filename cannot be empty"

class TestApplyExtensionPreservation:
    """Tests for apply_extension_preservation function."""

    def test_combines_stem_and_ext(self) -> None:
        """Combines stem and extension."""
        assert apply_extension_preservation("hero", ".png") == "hero.png"
        assert apply_extension_preservation("config", ".json") == "config.json"

    def test_no_extension(self) -> None:
        """Works with empty extension."""
        assert apply_extension_preservation("README", "") == "README"
        assert apply_extension_preservation(".gitignore", "") == ".gitignore"

    def test_strips_stem_whitespace(self) -> None:
        """Strips whitespace from stem."""
        assert apply_extension_preservation("  hero  ", ".png") == "hero.png"

class TestBuildNewPath:
    """Tests for build_new_path function."""

    def test_preserves_directory(self) -> None:
        """Preserves directory from original path."""
        result = build_new_path("assets/sprites/hero.png", "player.png")
        assert result == "assets/sprites/player.png"

    def test_root_file(self) -> None:
        """Root level file."""
        result = build_new_path("config.json", "settings.json")
        assert result == "settings.json"

    def test_nested_directory(self) -> None:
        """Deeply nested path."""
        result = build_new_path("a/b/c/d/file.txt", "new.txt")
        assert result == "a/b/c/d/new.txt"


class TestCreateInlineRenameState:
    """Tests for create_inline_rename_state function."""

    def test_creates_valid_state(self) -> None:
        """Creates state for valid path."""
        state = create_inline_rename_state("assets/hero.png")
        assert state is not None
        assert state.original_path == "assets/hero.png"
        assert state.original_basename == "hero.png"
        assert state.original_stem == "hero"
        assert state.original_ext == ".png"
        assert state.current_text == "hero"
        assert state.selection_start == 0
        assert state.selection_end == 4

    def test_returns_none_for_invalid(self) -> None:
        """Returns None for invalid path."""
        assert create_inline_rename_state("") is None
        assert create_inline_rename_state("folder/") is None

    def test_dotfile_state(self) -> None:
        """Creates state for dotfile."""
        state = create_inline_rename_state(".gitignore")
        assert state is not None
        assert state.original_stem == ".gitignore"
        assert state.original_ext == ""
        assert state.current_text == ".gitignore"


class TestUpdateRenameText:
    """Tests for update_rename_text function."""

    def test_replaces_text(self) -> None:
        """Replaces current text entirely."""
        state = create_inline_rename_state("hero.png")
        assert state is not None
        
        new_state = update_rename_text(state, "player")
        assert new_state.current_text == "player"
        assert new_state.selection_start == 6
        assert new_state.selection_end == 6

    def test_sanitizes_input(self) -> None:
        """Sanitizes invalid characters."""
        state = create_inline_rename_state("hero.png")
        assert state is not None
        
        new_state = update_rename_text(state, "play<er>")
        assert new_state.current_text == "player"


class TestAppendRenameText:
    """Tests for append_rename_text function."""

    def test_replaces_selection(self) -> None:
        """Replaces selection when text selected."""
        state = create_inline_rename_state("hero.png")
        assert state is not None
        # Initially entire stem is selected (0, 4)
        
        new_state = append_rename_text(state, "player")
        assert new_state.current_text == "player"
        assert new_state.selection_start == 6
        assert new_state.selection_end == 6

    def test_inserts_at_cursor(self) -> None:
        """Inserts at cursor when no selection."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=4,  # At end
            selection_end=4,
        )
        
        new_state = append_rename_text(state, "2")
        assert new_state.current_text == "hero2"
        assert new_state.selection_start == 5
        assert new_state.selection_end == 5


class TestHandleRenameBackspace:
    """Tests for handle_rename_backspace function."""

    def test_deletes_selection(self) -> None:
        """Deletes selection when text selected."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=1,
            selection_end=3,  # "er" selected
        )
        
        new_state = handle_rename_backspace(state)
        assert new_state.current_text == "ho"
        assert new_state.selection_start == 1
        assert new_state.selection_end == 1

    def test_deletes_char_before_cursor(self) -> None:
        """Deletes character before cursor when no selection."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=4,
            selection_end=4,
        )
        
        new_state = handle_rename_backspace(state)
        assert new_state.current_text == "her"
        assert new_state.selection_start == 3
        assert new_state.selection_end == 3

    def test_at_start_does_nothing(self) -> None:
        """Does nothing when cursor at start."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=0,
            selection_end=0,
        )
        
        new_state = handle_rename_backspace(state)
        assert new_state.current_text == "hero"
        assert new_state.selection_start == 0


class TestHandleRenameDelete:
    """Tests for handle_rename_delete function."""

    def test_deletes_selection(self) -> None:
        """Deletes selection when text selected."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=1,
            selection_end=3,
        )
        
        new_state = handle_rename_delete(state)
        assert new_state.current_text == "ho"

    def test_deletes_char_after_cursor(self) -> None:
        """Deletes character after cursor when no selection."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=0,
            selection_end=0,
        )
        
        new_state = handle_rename_delete(state)
        assert new_state.current_text == "ero"
        assert new_state.selection_start == 0

    def test_at_end_does_nothing(self) -> None:
        """Does nothing when cursor at end."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="hero",
            selection_start=4,
            selection_end=4,
        )
        
        new_state = handle_rename_delete(state)
        assert new_state.current_text == "hero"


class TestGetFinalRenameName:
    """Tests for get_final_rename_name function."""

    def test_combines_text_and_ext(self) -> None:
        """Combines current text with extension."""
        state = InlineRenameState(
            original_path="hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="player",
            selection_start=6,
            selection_end=6,
        )
        
        assert get_final_rename_name(state) == "player.png"


class TestGetFinalRenamePath:
    """Tests for get_final_rename_path function."""

    def test_builds_full_path(self) -> None:
        """Builds full path with directory."""
        state = InlineRenameState(
            original_path="assets/sprites/hero.png",
            original_basename="hero.png",
            original_stem="hero",
            original_ext=".png",
            current_text="player",
            selection_start=6,
            selection_end=6,
        )
        
        assert get_final_rename_path(state) == "assets/sprites/player.png"


class TestInlineRenameStateImmutability:
    """Tests verifying InlineRenameState is immutable."""

    def test_dataclass_is_frozen(self) -> None:
        """State cannot be mutated."""
        state = create_inline_rename_state("hero.png")
        assert state is not None
        
        with pytest.raises(AttributeError):
            state.current_text = "modified"  # type: ignore


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_file_starting_with_number(self) -> None:
        """File starting with number."""
        state = create_inline_rename_state("123file.txt")
        assert state is not None
        assert state.original_stem == "123file"

    def test_file_with_spaces(self) -> None:
        """File with spaces in name."""
        state = create_inline_rename_state("my file.txt")
        assert state is not None
        assert state.original_stem == "my file"

    def test_unicode_filename(self) -> None:
        """Unicode characters in filename."""
        state = create_inline_rename_state("héro.png")
        assert state is not None
        assert state.original_stem == "héro"

    def test_very_long_extension(self) -> None:
        """File with long extension."""
        stem, ext, basename = compute_initial_rename_text("file.longextension")
        assert stem == "file"
        assert ext == ".longextension"

    def test_only_extension(self) -> None:
        """File that is only an extension (dotfile)."""
        stem, ext, basename = compute_initial_rename_text(".hidden")
        assert stem == ".hidden"
        assert ext == ""
        assert basename == ".hidden"

    def test_backslash_path_handling(self) -> None:
        """Windows-style backslash paths are normalized."""
        state = create_inline_rename_state("assets\\sprites\\hero.png")
        assert state is not None
        assert state.original_path == "assets/sprites/hero.png"


class TestCursorMovement:
    """Tests for cursor movement functions."""

    def _make_state(self, text: str, sel_start: int, sel_end: int, anchor: int | None = None) -> InlineRenameState:
        """Create a test state with specific cursor/selection position."""
        return InlineRenameState(
            original_path="test.txt",
            original_basename="test.txt",
            original_stem="test",
            original_ext=".txt",
            current_text=text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )

    def test_move_left_from_middle(self) -> None:
        """Move left from middle of text collapses selection and moves."""
        state = self._make_state("hello", 3, 3)
        result = move_cursor_left(state, shift=False)
        assert result.selection_start == 2
        assert result.selection_end == 2
        assert result.anchor_idx is None

    def test_move_left_at_start_boundary(self) -> None:
        """Move left at start stays at 0."""
        state = self._make_state("hello", 0, 0)
        result = move_cursor_left(state, shift=False)
        assert result.selection_start == 0
        assert result.selection_end == 0

    def test_move_left_collapses_selection(self) -> None:
        """Move left with selection collapses to start of selection."""
        state = self._make_state("hello", 1, 4)
        result = move_cursor_left(state, shift=False)
        assert result.selection_start == 1
        assert result.selection_end == 1
        assert result.anchor_idx is None

    def test_move_right_from_middle(self) -> None:
        """Move right from middle of text."""
        state = self._make_state("hello", 2, 2)
        result = move_cursor_right(state, shift=False)
        assert result.selection_start == 3
        assert result.selection_end == 3

    def test_move_right_at_end_boundary(self) -> None:
        """Move right at end stays at end."""
        state = self._make_state("hello", 5, 5)
        result = move_cursor_right(state, shift=False)
        assert result.selection_start == 5
        assert result.selection_end == 5

    def test_move_right_collapses_selection(self) -> None:
        """Move right with selection collapses to end of selection."""
        state = self._make_state("hello", 1, 4)
        result = move_cursor_right(state, shift=False)
        assert result.selection_start == 4
        assert result.selection_end == 4

    def test_move_home(self) -> None:
        """Home moves to start of text."""
        state = self._make_state("hello", 3, 3)
        result = move_cursor_home(state, shift=False)
        assert result.selection_start == 0
        assert result.selection_end == 0
        assert result.anchor_idx is None

    def test_move_end(self) -> None:
        """End moves to end of text."""
        state = self._make_state("hello", 2, 2)
        result = move_cursor_end(state, shift=False)
        assert result.selection_start == 5
        assert result.selection_end == 5
        assert result.anchor_idx is None


class TestShiftSelection:
    """Tests for shift-selection (extending selection)."""

    def _make_state(self, text: str, sel_start: int, sel_end: int, anchor: int | None = None) -> InlineRenameState:
        """Create a test state with specific cursor/selection position."""
        return InlineRenameState(
            original_path="test.txt",
            original_basename="test.txt",
            original_stem="test",
            original_ext=".txt",
            current_text=text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )

    def test_shift_left_sets_anchor_and_extends(self) -> None:
        """Shift+Left from no selection sets anchor and extends left."""
        state = self._make_state("hello", 3, 3)
        result = move_cursor_left(state, shift=True)
        assert result.anchor_idx == 3  # Anchor set at original caret
        assert result.selection_start == 2
        assert result.selection_end == 3  # Selection from 2 to anchor 3

    def test_shift_left_preserves_anchor(self) -> None:
        """Shift+Left with existing anchor preserves it and extends selection."""
        # State with selection from 2 to 4, anchor at 2 (caret at sel_end=4)
        state = self._make_state("hello", 2, 4, anchor=2)
        result = move_cursor_left(state, shift=True)
        assert result.anchor_idx == 2  # Anchor preserved
        assert result.selection_start == 2  # min(anchor=2, new_caret=3)
        assert result.selection_end == 3  # max(anchor=2, new_caret=3)

    def test_shift_right_extends_selection(self) -> None:
        """Shift+Right extends selection to the right."""
        state = self._make_state("hello", 1, 1)
        result = move_cursor_right(state, shift=True)
        assert result.anchor_idx == 1
        assert result.selection_start == 1
        assert result.selection_end == 2

    def test_shift_home_selects_to_start(self) -> None:
        """Shift+Home selects from current position to start."""
        state = self._make_state("hello", 3, 3)
        result = move_cursor_home(state, shift=True)
        assert result.anchor_idx == 3
        assert result.selection_start == 0
        assert result.selection_end == 3

    def test_shift_end_selects_to_end(self) -> None:
        """Shift+End selects from current position to end."""
        state = self._make_state("hello", 2, 2)
        result = move_cursor_end(state, shift=True)
        assert result.anchor_idx == 2
        assert result.selection_start == 2
        assert result.selection_end == 5

    def test_shift_selection_can_reverse(self) -> None:
        """Shift selection can be reversed by moving past anchor."""
        # Start at position 3, shift+right to 4
        state = self._make_state("hello", 3, 3)
        result = move_cursor_right(state, shift=True)
        assert result.anchor_idx == 3
        assert result.selection_start == 3
        assert result.selection_end == 4
        
        # Now shift+left back past anchor
        result2 = move_cursor_left(result, shift=True)  # caret at 3
        result3 = move_cursor_left(result2, shift=True)  # caret at 2
        assert result3.anchor_idx == 3
        assert result3.selection_start == 2
        assert result3.selection_end == 3

    def test_non_shift_clears_anchor(self) -> None:
        """Non-shift movement clears anchor."""
        state = self._make_state("hello", 2, 4, anchor=2)
        result = move_cursor_left(state, shift=False)
        assert result.anchor_idx is None
        assert result.selection_start == 2
        assert result.selection_end == 2


class TestCursorDeterminism:
    """Tests verifying cursor operations are deterministic."""

    def _make_state(self, text: str, sel_start: int, sel_end: int, anchor: int | None = None) -> InlineRenameState:
        """Create a test state with specific cursor/selection position."""
        return InlineRenameState(
            original_path="test.txt",
            original_basename="test.txt",
            original_stem="test",
            original_ext=".txt",
            current_text=text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )

    def test_repeated_operations_deterministic(self) -> None:
        """Same operation on same state produces same result."""
        state = self._make_state("hello", 3, 3)
        result1 = move_cursor_left(state, shift=True)
        result2 = move_cursor_left(state, shift=True)
        assert result1 == result2

    def test_selection_bounds_always_ordered(self) -> None:
        """selection_start is always <= selection_end."""
        state = self._make_state("hello", 4, 4)
        # Move left with shift multiple times
        for _ in range(10):
            state = move_cursor_left(state, shift=True)
            assert state.selection_start <= state.selection_end
        # Move right with shift multiple times
        for _ in range(10):
            state = move_cursor_right(state, shift=True)
            assert state.selection_start <= state.selection_end


class TestWordNavigation:
    """Tests for word boundary navigation and deletion."""

    def _make_state(self, text: str, sel_start: int, sel_end: int, anchor: int | None = None) -> InlineRenameState:
        return InlineRenameState(
            original_path="test.txt",
            original_basename="test.txt",
            original_stem="test",
            original_ext=".txt",
            current_text=text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )

    def test_is_word_char(self) -> None:
        assert is_word_char("a") is True
        assert is_word_char("Z") is True
        assert is_word_char("9") is True
        assert is_word_char("_") is True
        assert is_word_char("-") is False
        assert is_word_char(".") is False

    def test_word_boundaries_across_separators(self) -> None:
        text = "hero_sprite.v2.png"
        # Next word from start should be v2
        assert find_next_word_boundary(text, 0) == len("hero_sprite") + 1
        # Prev word from end should be png start
        assert find_prev_word_boundary(text, len(text)) == len(text) - len("png")

    def test_word_boundaries_with_underscore(self) -> None:
        text = "hero_sprite"
        # Underscore is part of the word
        assert find_prev_word_boundary(text, len(text)) == 0

    def test_move_cursor_word_left(self) -> None:
        text = "hero_sprite.v2.png"
        state = self._make_state(text, len(text), len(text))
        result = move_cursor_word_left(state, shift=False)
        assert result.selection_start == len(text) - len("png")
        assert result.selection_end == len(text) - len("png")

    def test_move_cursor_word_right(self) -> None:
        text = "hero_sprite.v2.png"
        start = 0
        state = self._make_state(text, start, start)
        result = move_cursor_word_right(state, shift=False)
        assert result.selection_start == len("hero_sprite") + 1
        assert result.selection_end == len("hero_sprite") + 1

    def test_word_left_extend_selection(self) -> None:
        text = "hero_sprite.v2.png"
        state = self._make_state(text, len(text), len(text))
        result = move_cursor_word_left(state, shift=True)
        assert result.anchor_idx == len(text)
        assert result.selection_start == len(text) - len("png")
        assert result.selection_end == len(text)

    def test_word_right_extend_selection(self) -> None:
        text = "hero_sprite.v2.png"
        state = self._make_state(text, 0, 0)
        result = move_cursor_word_right(state, shift=True)
        assert result.anchor_idx == 0
        assert result.selection_start == 0
        assert result.selection_end == len("hero_sprite") + 1

    def test_delete_prev_word(self) -> None:
        text = "hero_sprite.v2.png"
        state = self._make_state(text, len(text), len(text))
        result = delete_prev_word(state)
        assert result.current_text == "hero_sprite.v2."
        assert result.selection_start == len("hero_sprite.v2.")
        assert result.selection_end == len("hero_sprite.v2.")

    def test_delete_next_word(self) -> None:
        text = "hero_sprite.v2.png"
        caret = len("hero_sprite.")
        state = self._make_state(text, caret, caret)
        result = delete_next_word(state)
        assert result.current_text == "hero_sprite.png"
        assert result.selection_start == caret
        assert result.selection_end == caret

    def test_delete_selection_precedence(self) -> None:
        text = "hero_sprite"
        state = self._make_state(text, 1, 4)
        result_prev = delete_prev_word(state)
        result_next = delete_next_word(state)
        assert result_prev.current_text == "h_sprite"
        assert result_next.current_text == "h_sprite"

    def test_word_ops_deterministic(self) -> None:
        text = "hero_sprite.v2.png"
        state = self._make_state(text, len(text), len(text))
        result1 = move_cursor_word_left(state, shift=True)
        result2 = move_cursor_word_left(state, shift=True)
        assert result1 == result2
