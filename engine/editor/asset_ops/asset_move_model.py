"""Pure model helpers for safe asset move.

Provides deterministic functions for:
- Computing new paths when moving an asset
- Validating move destinations
- Formatting undo labels
"""

from __future__ import annotations

import os

def _normalize_path(path: str) -> str:
    """Normalize a path for comparison (forward slashes, stripped)."""
    if not path:
        return ""
    return path.strip().replace("\\", "/")

def compute_move_paths(old_rel: str, dest_folder_rel: str) -> tuple[str, str]:
    """Compute old and new relative paths for a move operation.

    Args:
        old_rel: Current relative path (e.g. "assets/hero.png")
        dest_folder_rel: Destination folder relative path (e.g. "assets/characters")

    Returns:
        Tuple of (normalized_old_path, normalized_new_path)
    """
    old_norm = _normalize_path(old_rel)
    dest_norm = _normalize_path(dest_folder_rel)

    if not old_norm:
        return ("", "")

    filename = os.path.basename(old_norm)
    
    if not dest_norm:
        # Move to root
        new_norm = filename
    else:
        new_norm = f"{dest_norm}/{filename}"

    return (old_norm, new_norm)

def validate_destination(old_rel: str, dest_folder_rel: str) -> tuple[bool, str]:
    """Validate if a move destination is valid.

    Args:
        old_rel: Current asset path
        dest_folder_rel: Destination folder path

    Returns:
        (is_valid, reason)
    """
    old_norm = _normalize_path(old_rel)
    dest_norm = _normalize_path(dest_folder_rel)

    if not old_norm:
        return False, "Invalid source path"

    # Check if moving to same folder
    current_dir = os.path.dirname(old_norm).replace("\\", "/")
    if not current_dir:
        current_dir = ""
    
    # Normalize empty string handling
    if current_dir == dest_norm:
        return False, "Destination is the same as source folder"

    # Check if moving into itself (if old_rel is a folder, which we don't support yet but good to guard)
    # The requirement says "selected file path", so assuming file.
    
    return True, ""

def format_move_undo_label(old_rel: str, new_rel: str, n_refs: int) -> str:
    """Format an undo label for a move operation.

    Args:
        old_rel: Old path
        new_rel: New path
        n_refs: Number of references updated

    Returns:
        Undo label string
    """
    old_name = os.path.basename(old_rel)
    # new_folder = os.path.dirname(new_rel).replace("\\", "/")
    
    # "Move hero.png to assets/new_folder"
    if n_refs == 0:
        return f"Move {old_name} → {new_rel}"
    
    return f"Move {old_name} → {new_rel} ({n_refs} refs)"
