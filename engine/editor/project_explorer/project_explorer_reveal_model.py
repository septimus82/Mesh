"""Pure model helpers for Project Explorer reveal and copy path features.

Provides:
- choose_reveal_target: Deterministic target selection for reveal
- compute_reveal_scroll_index: Compute row index to scroll to
- normalize_repo_relative_path: Normalize paths for comparison
- format_copy_path_text: Format path for clipboard
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

__all__ = [
    "choose_reveal_target",
    "compute_reveal_scroll_index",
    "find_row_index_for_path",
    "normalize_repo_relative_path",
    "format_copy_path_text",
]

T = TypeVar("T")


def normalize_repo_relative_path(path: str | None) -> str:
    """Normalize a path for repo-relative comparison.

    - Strips whitespace
    - Converts backslashes to forward slashes
    - Removes leading/trailing slashes
    - Returns empty string for None/empty

    Deterministic: same input always produces same output.
    """
    if not path:
        return ""
    normalized = str(path).strip()
    # Convert backslashes to forward slashes
    normalized = normalized.replace("\\", "/")
    # Remove leading/trailing slashes
    normalized = normalized.strip("/")
    return normalized


def choose_reveal_target(
    scene_path: str | None,
    entity_asset_path: str | None,
) -> str | None:
    """Choose the best reveal target with deterministic priority.

    Priority order:
    1. Current scene file path (if present)
    2. Selected entity's sprite/asset path (if present)

    Args:
        scene_path: Path to the currently loaded scene file.
        entity_asset_path: Path to the selected entity's asset (sprite, etc.).

    Returns:
        Normalized path to reveal, or None if no valid target.

    Deterministic: same inputs always produce same output.
    """
    # Priority 1: Current scene path
    scene_norm = normalize_repo_relative_path(scene_path)
    if scene_norm:
        return scene_norm

    # Priority 2: Entity asset path
    asset_norm = normalize_repo_relative_path(entity_asset_path)
    if asset_norm:
        return asset_norm

    return None


def find_row_index_for_path(
    rows: Sequence[T],
    target_path: str,
    get_path_fn: Callable[[T], str],
) -> int | None:
    """Find the index of the row matching target_path.

    Args:
        rows: Sequence of row objects.
        target_path: The normalized path to find.
        get_path_fn: Function to extract path from a row.

    Returns:
        Index of matching row, or None if not found.

    Deterministic: same inputs always produce same output.
    """
    target_norm = normalize_repo_relative_path(target_path)
    if not target_norm:
        return None

    for idx, row in enumerate(rows):
        row_path = normalize_repo_relative_path(get_path_fn(row))
        if row_path == target_norm:
            return idx

    return None


def compute_reveal_scroll_index(
    rows: Sequence[T],
    target_path: str,
    get_path_fn: Callable[[T], str],
    visible_count: int,
) -> tuple[int | None, int]:
    """Compute the row index and scroll start for revealing a target path.

    Places the target row near the center of the viewport when possible.

    Args:
        rows: Sequence of row objects.
        target_path: The normalized path to reveal.
        get_path_fn: Function to extract path from a row.
        visible_count: Number of rows visible in viewport.

    Returns:
        Tuple of (row_index, scroll_start_index):
        - row_index: Index of the target row, or None if not found.
        - scroll_start_index: Index to start scrolling from (0 if not found).

    Deterministic: same inputs always produce same output.
    """
    row_index = find_row_index_for_path(rows, target_path, get_path_fn)
    if row_index is None:
        return (None, 0)

    total_rows = len(rows)
    if total_rows == 0 or visible_count <= 0:
        return (row_index, 0)

    # Center the target row in the viewport
    half_visible = visible_count // 2
    scroll_start = max(0, row_index - half_visible)

    # Clamp to ensure we don't scroll past the end
    max_start = max(0, total_rows - visible_count)
    scroll_start = min(scroll_start, max_start)

    return (row_index, scroll_start)


def format_copy_path_text(path: str | None) -> str:
    """Format a path for copying to clipboard.

    Returns the normalized repo-relative path.

    Args:
        path: The path to format.

    Returns:
        Normalized path string, or empty string if no path.

    Deterministic: same input always produces same output.
    """
    return normalize_repo_relative_path(path)
