"""Pure model helpers for inline rename UX in Project Explorer.

Provides deterministic functions for:
- Checking if a path is renameable
- Splitting filename into basename and extension
- Computing initial rename text and selection
- Sanitizing user input
- Applying extension preservation
- Determining commit validity

All functions are pure (no I/O, no side effects) for easy testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional

__all__ = [
    "is_renameable_path",
    "split_basename_ext",
    "compute_initial_rename_text",
    "sanitize_rename_input",
    "should_commit_rename",
    "apply_extension_preservation",
    "compute_rename_selection",
    "InlineRenameState",
    "INVALID_FILENAME_CHARS",
    "move_cursor_left",
    "move_cursor_right",
    "move_cursor_home",
    "move_cursor_end",
    "is_word_char",
    "find_prev_word_boundary",
    "find_next_word_boundary",
    "move_cursor_word_left",
    "move_cursor_word_right",
    "delete_prev_word",
    "delete_next_word",
    "normalize_committed_filename",
    "is_reserved_filename",
    "contains_path_separators",
]

# Characters not allowed in filenames (Windows-compatible)
INVALID_FILENAME_CHARS = frozenset('<>:"/\\|?*')

# Characters that also shouldn't appear in portable filenames
DISCOURAGED_FILENAME_CHARS = frozenset('\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r')


@dataclass(frozen=True, slots=True)
class InlineRenameState:
    """Immutable state for an active inline rename session.
    
    Attributes:
        original_path: The original relative path being renamed.
        original_basename: The original filename without directory.
        original_stem: The editable portion (before extension).
        original_ext: The extension to preserve (including dot, or empty).
        current_text: The current text in the editor (stem portion only).
        selection_start: Start index of selection in current_text.
        selection_end: End index of selection in current_text.
        anchor_idx: Anchor position for shift-selection (None if no anchor).
    
    The caret is always at selection_end. When shift-selecting, anchor_idx
    marks the fixed end of the selection while selection_end moves.
    """
    original_path: str
    original_basename: str
    original_stem: str
    original_ext: str
    current_text: str
    selection_start: int
    selection_end: int
    anchor_idx: Optional[int] = None


def _normalize_path(path: str) -> str:
    """Normalize path separators to forward slash."""
    if not path:
        return ""
    return path.replace("\\", "/").strip()


def is_renameable_path(path: str) -> bool:
    """Check if a path can be renamed.
    
    A path is renameable if:
    - It's not empty after normalization
    - It's a file path (doesn't end with /)
    - It has a filename component
    
    Args:
        path: The relative path to check.
        
    Returns:
        True if the path can be renamed, False otherwise.
    """
    norm = _normalize_path(path)
    if not norm:
        return False
    # Don't allow renaming directories
    if norm.endswith("/"):
        return False
    # Must have a filename
    filename = norm.rsplit("/", 1)[-1] if "/" in norm else norm
    return bool(filename)


def split_basename_ext(filename: str) -> Tuple[str, str]:
    """Split a filename into stem and extension.
    
    Handles dotfiles (files starting with .) specially:
    - ".gitignore" -> (".gitignore", "")
    - ".env.local" -> (".env", ".local")
    
    Handles multi-dot extensions:
    - "file.tar.gz" -> ("file", ".tar.gz") [NOT supported, uses last dot]
    - "file.tar.gz" -> ("file.tar", ".gz") [actual behavior]
    
    Args:
        filename: The filename (without directory).
        
    Returns:
        Tuple of (stem, extension) where extension includes the dot.
    """
    if not filename:
        return ("", "")
    
    # Handle dotfiles: if starts with dot and no other dots, keep whole name
    if filename.startswith("."):
        # Find dot after the leading dot
        rest = filename[1:]
        dot_pos = rest.rfind(".")
        if dot_pos == -1:
            # No extension (e.g., ".gitignore")
            return (filename, "")
        else:
            # Has extension after leading dot (e.g., ".env.local")
            stem = filename[:1 + dot_pos]  # "." + chars before last dot
            ext = filename[1 + dot_pos:]    # last dot and after
            return (stem, ext)
    
    # Normal file: split on last dot
    dot_pos = filename.rfind(".")
    if dot_pos == -1 or dot_pos == 0:
        # No extension
        return (filename, "")
    
    stem = filename[:dot_pos]
    ext = filename[dot_pos:]
    return (stem, ext)


def compute_initial_rename_text(path: str) -> Tuple[str, str, str]:
    """Compute the initial text for the rename editor.
    
    Args:
        path: The relative path being renamed.
        
    Returns:
        Tuple of (stem, extension, basename) where:
        - stem is the editable portion
        - extension is preserved (with dot, or empty)
        - basename is the full original filename
    """
    norm = _normalize_path(path)
    if not norm:
        return ("", "", "")
    
    # Extract filename
    basename = norm.rsplit("/", 1)[-1] if "/" in norm else norm
    stem, ext = split_basename_ext(basename)
    
    return (stem, ext, basename)


def compute_rename_selection(stem: str) -> Tuple[int, int]:
    """Compute the initial selection range for the rename editor.
    
    By default, selects the entire stem for easy replacement.
    
    Args:
        stem: The editable stem portion.
        
    Returns:
        Tuple of (start, end) indices for selection.
    """
    return (0, len(stem))


def sanitize_rename_input(text: str) -> str:
    """Sanitize user input for rename.
    
    Removes invalid filename characters.
    
    Args:
        text: The raw user input.
        
    Returns:
        Sanitized text safe for use as a filename stem.
    """
    if not text:
        return ""
    
    result = []
    for ch in text:
        if ch in INVALID_FILENAME_CHARS:
            continue
        if ch in DISCOURAGED_FILENAME_CHARS:
            continue
        # Don't allow path separators in the stem
        if ch == "/" or ch == "\\":
            continue
        result.append(ch)
    
    return "".join(result)


def normalize_committed_filename(name: str) -> str:
    """Normalize a committed filename for cross-platform safety.

    - Strip leading/trailing whitespace
    - Trim trailing spaces and dots repeatedly
    """
    if not name:
        return ""
    normalized = name.strip()
    while normalized.endswith(" ") or normalized.endswith("."):
        normalized = normalized[:-1]
    return normalized


def is_reserved_filename(name: str) -> bool:
    """Return True if the filename is reserved/invalid.

    Rejects empty string, ".", "..", and names containing path separators.
    """
    if not name:
        return True
    if name in {".", ".."}:
        return True
    if "/" in name or "\\" in name:
        return True
    return False


def contains_path_separators(name: str) -> bool:
    """Return True if name contains path separators or drive-ish chars.

    Rejects '/', '\\', and ':'
    """
    if not name:
        return False
    return "/" in name or "\\" in name or ":" in name


def should_commit_rename(
    original_stem: str,
    current_text: str,
    original_ext: str,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Determine if a rename should be committed.
    
    Args:
        original_stem: The original filename stem.
        current_text: The current text in the editor.
        original_ext: The preserved extension.
        
    Returns:
        Tuple of (should_commit, normalized_name, error_message).
        If should_commit is False, normalized_name is None and error_message explains why.
    """
    # Reject path separators / drive-ish characters in raw input
    if contains_path_separators(current_text):
        return (False, None, "Filename cannot be empty")

    # Sanitize the editable part
    sanitized = sanitize_rename_input(current_text)
    stem_normalized = normalize_committed_filename(sanitized)

    # Reject empty stem after sanitization/normalization
    if not stem_normalized:
        return (False, None, "Filename cannot be empty")

    # Build candidate name with extension preservation
    candidate = apply_extension_preservation(stem_normalized, original_ext)
    normalized = normalize_committed_filename(candidate)

    # Cannot be empty or reserved after normalization
    if is_reserved_filename(normalized):
        return (False, None, "Filename cannot be empty")

    # Reject path separators / drive-ish characters
    if contains_path_separators(normalized):
        return (False, None, "Filename cannot be empty")

    # Check for invalid characters (shouldn't happen if sanitize is used)
    for ch in INVALID_FILENAME_CHARS:
        if ch in normalized:
            return (False, None, f"Invalid character: {ch}")

    # Check if name actually changed
    old_name = original_stem + original_ext
    if normalized == old_name:
        return (False, None, None)  # No error, just no change

    return (True, normalized, None)


def apply_extension_preservation(stem: str, ext: str) -> str:
    """Combine stem and extension into final filename.
    
    Args:
        stem: The edited stem (will be stripped).
        ext: The extension to append.
        
    Returns:
        The complete filename.
    """
    return stem.strip() + ext


def build_new_path(original_path: str, new_basename: str) -> str:
    """Build the new relative path from original path and new basename.
    
    Args:
        original_path: The original relative path.
        new_basename: The new filename (stem + ext).
        
    Returns:
        The new relative path with same directory.
    """
    norm = _normalize_path(original_path)
    if not norm:
        return new_basename
    
    if "/" in norm:
        directory = norm.rsplit("/", 1)[0]
        return f"{directory}/{new_basename}"
    else:
        return new_basename


def create_inline_rename_state(path: str) -> Optional[InlineRenameState]:
    """Create an initial inline rename state for a path.
    
    Args:
        path: The relative path to rename.
        
    Returns:
        InlineRenameState if path is renameable, None otherwise.
    """
    if not is_renameable_path(path):
        return None
    
    stem, ext, basename = compute_initial_rename_text(path)
    sel_start, sel_end = compute_rename_selection(stem)
    
    return InlineRenameState(
        original_path=_normalize_path(path),
        original_basename=basename,
        original_stem=stem,
        original_ext=ext,
        current_text=stem,
        selection_start=sel_start,
        selection_end=sel_end,
    )


def update_rename_text(state: InlineRenameState, new_text: str) -> InlineRenameState:
    """Update the rename state with new text (replaces selection or appends).
    
    Args:
        state: The current rename state.
        new_text: The new text to set.
        
    Returns:
        New InlineRenameState with updated text.
    """
    sanitized = sanitize_rename_input(new_text)
    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=sanitized,
        selection_start=len(sanitized),
        selection_end=len(sanitized),
    )


def append_rename_text(state: InlineRenameState, text: str) -> InlineRenameState:
    """Append text to the current rename text.
    
    If there's a selection, replaces it. Otherwise appends at cursor.
    
    Args:
        state: The current rename state.
        text: The text to append.
        
    Returns:
        New InlineRenameState with updated text.
    """
    sanitized = sanitize_rename_input(text)
    if not sanitized:
        return state
    
    current = state.current_text
    sel_start = state.selection_start
    sel_end = state.selection_end
    
    # Replace selection or insert at cursor
    if sel_start != sel_end:
        # Replace selection
        new_text = current[:sel_start] + sanitized + current[sel_end:]
        new_cursor = sel_start + len(sanitized)
    else:
        # Insert at cursor position
        new_text = current[:sel_start] + sanitized + current[sel_start:]
        new_cursor = sel_start + len(sanitized)
    
    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=new_text,
        selection_start=new_cursor,
        selection_end=new_cursor,
    )


def handle_rename_backspace(state: InlineRenameState) -> InlineRenameState:
    """Handle backspace key in rename editor.
    
    If there's a selection, deletes it. Otherwise deletes char before cursor.
    
    Args:
        state: The current rename state.
        
    Returns:
        New InlineRenameState with updated text.
    """
    current = state.current_text
    sel_start = state.selection_start
    sel_end = state.selection_end
    
    if sel_start != sel_end:
        # Delete selection
        new_text = current[:sel_start] + current[sel_end:]
        new_cursor = sel_start
    elif sel_start > 0:
        # Delete char before cursor
        new_text = current[:sel_start - 1] + current[sel_start:]
        new_cursor = sel_start - 1
    else:
        # At start, nothing to delete
        return state
    
    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=new_text,
        selection_start=new_cursor,
        selection_end=new_cursor,
    )


def handle_rename_delete(state: InlineRenameState) -> InlineRenameState:
    """Handle delete key in rename editor.
    
    If there's a selection, deletes it. Otherwise deletes char after cursor.
    
    Args:
        state: The current rename state.
        
    Returns:
        New InlineRenameState with updated text.
    """
    current = state.current_text
    sel_start = state.selection_start
    sel_end = state.selection_end
    
    if sel_start != sel_end:
        # Delete selection
        new_text = current[:sel_start] + current[sel_end:]
        new_cursor = sel_start
    elif sel_start < len(current):
        # Delete char after cursor
        new_text = current[:sel_start] + current[sel_start + 1:]
        new_cursor = sel_start
    else:
        # At end, nothing to delete
        return state
    
    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=new_text,
        selection_start=new_cursor,
        selection_end=new_cursor,
    )


def get_final_rename_name(state: InlineRenameState) -> str:
    """Get the final filename from current state.
    
    Args:
        state: The current rename state.
        
    Returns:
        The final filename (stem + extension).
    """
    return apply_extension_preservation(state.current_text, state.original_ext)


def get_final_rename_path(state: InlineRenameState) -> str:
    """Get the final relative path from current state.
    
    Args:
        state: The current rename state.
        
    Returns:
        The final relative path.
    """
    new_name = get_final_rename_name(state)
    return build_new_path(state.original_path, new_name)


def _get_caret_position(state: InlineRenameState) -> int:
    """Get the current caret position (always at selection_end)."""
    return state.selection_end


def _compute_selection(anchor: int, caret: int) -> Tuple[int, int]:
    """Compute selection bounds from anchor and caret.
    
    Returns (start, end) where start <= end.
    """
    return (min(anchor, caret), max(anchor, caret))


def is_word_char(ch: str) -> bool:
    """Return True if a character is part of a word.

    Word characters are [A-Za-z0-9_].
    """
    if not ch:
        return False
    return ch.isalnum() or ch == "_"


def find_prev_word_boundary(text: str, idx: int) -> int:
    """Find the start index of the previous word.

    Skips separators first, then moves left across word characters.
    """
    if not text:
        return 0
    i = max(0, min(idx, len(text)))
    # Skip separators
    while i > 0 and not is_word_char(text[i - 1]):
        i -= 1
    # Skip word characters
    while i > 0 and is_word_char(text[i - 1]):
        i -= 1
    return i


def find_next_word_boundary(text: str, idx: int) -> int:
    """Find the start index of the next word.

    Skips current word first, then separators.
    """
    if not text:
        return 0
    i = max(0, min(idx, len(text)))
    # Skip current word characters
    while i < len(text) and is_word_char(text[i]):
        i += 1
    # Skip separators
    while i < len(text) and not is_word_char(text[i]):
        i += 1
    return i


def move_cursor_left(state: InlineRenameState, shift: bool = False) -> InlineRenameState:
    """Move cursor left by one character.
    
    Args:
        state: The current rename state.
        shift: If True, extend selection; if False, collapse and move.
        
    Returns:
        New InlineRenameState with updated cursor/selection.
    """
    text_len = len(state.current_text)
    caret = _get_caret_position(state)
    
    if shift:
        # Extend selection: set anchor if not set, move caret left
        anchor = state.anchor_idx if state.anchor_idx is not None else caret
        new_caret = max(0, caret - 1)
        sel_start, sel_end = _compute_selection(anchor, new_caret)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )
    else:
        # Collapse selection and move left
        if state.selection_start != state.selection_end:
            # Collapse to start of selection
            new_pos = state.selection_start
        else:
            # Move left by one
            new_pos = max(0, caret - 1)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=new_pos,
            selection_end=new_pos,
            anchor_idx=None,
        )


def move_cursor_right(state: InlineRenameState, shift: bool = False) -> InlineRenameState:
    """Move cursor right by one character.
    
    Args:
        state: The current rename state.
        shift: If True, extend selection; if False, collapse and move.
        
    Returns:
        New InlineRenameState with updated cursor/selection.
    """
    text_len = len(state.current_text)
    caret = _get_caret_position(state)
    
    if shift:
        # Extend selection: set anchor if not set, move caret right
        anchor = state.anchor_idx if state.anchor_idx is not None else caret
        new_caret = min(text_len, caret + 1)
        sel_start, sel_end = _compute_selection(anchor, new_caret)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )
    else:
        # Collapse selection and move right
        if state.selection_start != state.selection_end:
            # Collapse to end of selection
            new_pos = state.selection_end
        else:
            # Move right by one
            new_pos = min(text_len, caret + 1)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=new_pos,
            selection_end=new_pos,
            anchor_idx=None,
        )


def move_cursor_home(state: InlineRenameState, shift: bool = False) -> InlineRenameState:
    """Move cursor to start of text.
    
    Args:
        state: The current rename state.
        shift: If True, extend selection; if False, collapse and move.
        
    Returns:
        New InlineRenameState with updated cursor/selection.
    """
    caret = _get_caret_position(state)
    
    if shift:
        # Extend selection from anchor to start
        anchor = state.anchor_idx if state.anchor_idx is not None else caret
        new_caret = 0
        sel_start, sel_end = _compute_selection(anchor, new_caret)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )
    else:
        # Move to start, no selection
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=0,
            selection_end=0,
            anchor_idx=None,
        )


def move_cursor_end(state: InlineRenameState, shift: bool = False) -> InlineRenameState:
    """Move cursor to end of text.
    
    Args:
        state: The current rename state.
        shift: If True, extend selection; if False, collapse and move.
        
    Returns:
        New InlineRenameState with updated cursor/selection.
    """
    text_len = len(state.current_text)
    caret = _get_caret_position(state)
    
    if shift:
        # Extend selection from anchor to end
        anchor = state.anchor_idx if state.anchor_idx is not None else caret
        new_caret = text_len
        sel_start, sel_end = _compute_selection(anchor, new_caret)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )
    else:
        # Move to end, no selection
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=text_len,
            selection_end=text_len,
            anchor_idx=None,
        )


def move_cursor_word_left(state: InlineRenameState, shift: bool = False) -> InlineRenameState:
    """Move cursor to previous word boundary.

    Args:
        state: The current rename state.
        shift: If True, extend selection; if False, collapse and move.

    Returns:
        New InlineRenameState with updated cursor/selection.
    """
    caret = _get_caret_position(state)
    new_caret = find_prev_word_boundary(state.current_text, caret)

    if shift:
        anchor = state.anchor_idx if state.anchor_idx is not None else caret
        sel_start, sel_end = _compute_selection(anchor, new_caret)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )

    if state.selection_start != state.selection_end:
        new_pos = state.selection_start
    else:
        new_pos = new_caret
    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=state.current_text,
        selection_start=new_pos,
        selection_end=new_pos,
        anchor_idx=None,
    )


def move_cursor_word_right(state: InlineRenameState, shift: bool = False) -> InlineRenameState:
    """Move cursor to next word boundary.

    Args:
        state: The current rename state.
        shift: If True, extend selection; if False, collapse and move.

    Returns:
        New InlineRenameState with updated cursor/selection.
    """
    caret = _get_caret_position(state)
    new_caret = find_next_word_boundary(state.current_text, caret)

    if shift:
        anchor = state.anchor_idx if state.anchor_idx is not None else caret
        sel_start, sel_end = _compute_selection(anchor, new_caret)
        return InlineRenameState(
            original_path=state.original_path,
            original_basename=state.original_basename,
            original_stem=state.original_stem,
            original_ext=state.original_ext,
            current_text=state.current_text,
            selection_start=sel_start,
            selection_end=sel_end,
            anchor_idx=anchor,
        )

    if state.selection_start != state.selection_end:
        new_pos = state.selection_end
    else:
        new_pos = new_caret
    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=state.current_text,
        selection_start=new_pos,
        selection_end=new_pos,
        anchor_idx=None,
    )


def delete_prev_word(state: InlineRenameState) -> InlineRenameState:
    """Delete previous word or selection.

    If selection exists, delete selection first.
    """
    current = state.current_text
    sel_start = state.selection_start
    sel_end = state.selection_end
    caret = _get_caret_position(state)

    if sel_start != sel_end:
        new_text = current[:sel_start] + current[sel_end:]
        new_cursor = sel_start
    else:
        boundary = find_prev_word_boundary(current, caret)
        if boundary == caret:
            return state
        new_text = current[:boundary] + current[caret:]
        new_cursor = boundary

    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=new_text,
        selection_start=new_cursor,
        selection_end=new_cursor,
        anchor_idx=None,
    )


def delete_next_word(state: InlineRenameState) -> InlineRenameState:
    """Delete next word or selection.

    If selection exists, delete selection first.
    """
    current = state.current_text
    sel_start = state.selection_start
    sel_end = state.selection_end
    caret = _get_caret_position(state)

    if sel_start != sel_end:
        new_text = current[:sel_start] + current[sel_end:]
        new_cursor = sel_start
    else:
        boundary = find_next_word_boundary(current, caret)
        if boundary == caret:
            return state
        new_text = current[:caret] + current[boundary:]
        new_cursor = caret

    return InlineRenameState(
        original_path=state.original_path,
        original_basename=state.original_basename,
        original_stem=state.original_stem,
        original_ext=state.original_ext,
        current_text=new_text,
        selection_start=new_cursor,
        selection_end=new_cursor,
        anchor_idx=None,
    )
