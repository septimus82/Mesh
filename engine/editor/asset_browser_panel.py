"""Asset Browser panel helper functions.

This module provides pure functions for filtering, selecting, and building
display data for the asset browser. State management remains in EditorModeController.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from engine.asset_index import AssetRow


# Asset browser kind options
ASSET_BROWSER_KINDS = ("All", "Image", "Audio", "JSON")
ASSET_BROWSER_EMPTY_FOLDER_PLACEHOLDER = "No assets in this folder."
ASSET_BROWSER_NO_RESULTS_PLACEHOLDER_PREFIX = "No results for '"
ASSET_BROWSER_NO_RESULTS_PLACEHOLDER_SUFFIX = "'."


def filter_assets_for_browser(
    rows: List["AssetRow"],
    query: str,
    kind_filter: str,
) -> List["AssetRow"]:
    """Filter asset rows by search query and kind.

    Args:
        rows: List of asset rows to filter.
        query: Search text (case-insensitive substring match on path).
        kind_filter: Kind filter ("All", "Image", "Audio", "JSON").

    Returns:
        Filtered list of assets in deterministic order (preserves input order).
    """
    text = (query or "").strip().casefold()
    kind_target = (kind_filter or "All").lower()

    result: List["AssetRow"] = []
    for row in rows:
        # Kind filter
        if kind_target != "all" and row.kind != kind_target:
            continue

        # Text filter
        if text and text not in row.rel_path.casefold():
            continue

        result.append(row)

    return result


def clamp_asset_selection_index(index: int, count: int) -> int:
    """Clamp asset selection index to valid range.

    Args:
        index: Current selection index.
        count: Total number of items.

    Returns:
        Clamped index in range [0, count-1] or 0 if count is 0.
    """
    if count == 0:
        return 0
    return max(0, min(index, count - 1))


def compute_asset_browser_window(
    index: int,
    count: int,
    max_visible: int = 20,
) -> tuple[int, int]:
    """Compute the visible window range for scrolling.

    Args:
        index: Current selection index.
        count: Total number of items.
        max_visible: Maximum number of visible items.

    Returns:
        Tuple of (start_index, end_index).
    """
    if count == 0:
        return 0, 0

    scroll_offset = 0
    if index >= max_visible:
        scroll_offset = index - max_visible + 1

    start_idx = scroll_offset
    end_idx = min(count, start_idx + max_visible)
    return start_idx, end_idx


def build_asset_browser_lines(
    *,
    active: bool,
    search_text: str,
    search_focused: bool,
    kind_filter: str,
    rows: List["AssetRow"],
    selection_index: int,
) -> List[str]:
    """Build display lines for the asset browser panel.

    Args:
        active: Whether asset browser is active.
        search_text: Current search query.
        search_focused: Whether search input is focused.
        kind_filter: Current kind filter.
        rows: List of filtered asset rows.
        selection_index: Current selection index.

    Returns:
        List of strings to display in the asset browser panel.
    """
    if not active:
        return []

    lines: List[str] = []
    lines.append("ASSET BROWSER")
    lines.append("-------------")
    from .panel_search_model import format_search_bar_text  # noqa: PLC0415

    lines.append(format_search_bar_text(search_text, search_focused))
    lines.append(f"Filter (Tab): {kind_filter}")
    lines.append("-------------")

    if not rows:
        lines.append(f"  {_format_asset_browser_empty_placeholder(search_text)}")
        return lines

    max_visible = 19
    start_idx, end_idx = compute_asset_browser_window(selection_index, len(rows), max_visible)

    for i in range(start_idx, end_idx):
        row = rows[i]
        prefix = "> " if i == selection_index else "  "
        lines.append(f"{prefix}{row.display_name} [{row.kind}]")

    return lines


def _format_asset_browser_empty_placeholder(search_text: str) -> str:
    query = str(search_text or "").strip()
    if not query:
        return ASSET_BROWSER_EMPTY_FOLDER_PLACEHOLDER
    return (
        ASSET_BROWSER_NO_RESULTS_PLACEHOLDER_PREFIX
        + _escape_asset_browser_query(query)
        + ASSET_BROWSER_NO_RESULTS_PLACEHOLDER_SUFFIX
    )


def _escape_asset_browser_query(query: str) -> str:
    return query.replace("\\", "\\\\").replace("'", "\\'")


def cycle_asset_browser_kind(current_kind: str) -> str:
    """Cycle to the next asset browser kind filter.

    Args:
        current_kind: Current kind filter value.

    Returns:
        Next kind filter value in the cycle.
    """
    try:
        current_lower = current_kind.lower()
        current_idx = next(
            i for i, k in enumerate(ASSET_BROWSER_KINDS) if k.lower() == current_lower
        )
    except (ValueError, StopIteration):
        current_idx = 0

    new_idx = (current_idx + 1) % len(ASSET_BROWSER_KINDS)
    return ASSET_BROWSER_KINDS[new_idx]


def resolve_asset_activation(selected_row: "AssetRow") -> Dict[str, Any]:
    """Resolve what action to take when an asset is activated.

    Does not perform mutations - returns an intent dictionary describing
    what the controller should do.

    Args:
        selected_row: The selected asset row.

    Returns:
        Intent dictionary with one of:
        - {"kind": "spawn_entity", "asset_path": "...", "suggested_id": "..."}
        - {"kind": "copy_path", "asset_path": "..."}
    """
    if selected_row.kind == "image":
        # Extract suggested ID from filename
        import os
        basename = os.path.splitext(selected_row.display_name)[0]
        # Sanitize: alphanumeric and underscore only
        suggested_id = "".join(c if c.isalnum() else "_" for c in basename)
        if not suggested_id:
            suggested_id = "asset"

        return {
            "kind": "spawn_entity",
            "asset_path": selected_row.rel_path,
            "suggested_id": suggested_id,
        }
    else:
        return {
            "kind": "copy_path",
            "asset_path": selected_row.rel_path,
        }


def move_asset_selection(
    current_index: int,
    delta: int,
    count: int,
) -> int:
    """Move asset selection by delta with wrapping.

    Args:
        current_index: Current selection index.
        delta: Amount to move (positive or negative).
        count: Total number of items.

    Returns:
        New selection index with wrapping.
    """
    if count == 0:
        return 0
    return (current_index + delta) % count
