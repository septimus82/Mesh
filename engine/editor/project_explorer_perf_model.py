"""Performance helpers for Project Explorer: caching + visible-row slicing.

Provides:
- compute_filter_key: deterministic cache key from query + expanded_ids + tree_rev
- slice_visible_rows: viewport-based slicing with overscan
- estimate_total_height: height estimate for scroll container
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Sequence, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "compute_filter_key",
    "slice_visible_rows",
    "estimate_total_height",
    "SliceResult",
]

T = TypeVar("T")


class SliceResult(tuple[int, int, list[T]]):
    """Result of slice_visible_rows: (start_index, end_index, visible_rows)."""

    __slots__ = ()

    def __new__(cls, start: int, end: int, rows: list[T]) -> "SliceResult[T]":
        return super().__new__(cls, (start, end, rows))

    @property
    def start(self) -> int:
        return self[0]

    @property
    def end(self) -> int:
        return self[1]

    @property
    def rows(self) -> list[T]:
        return self[2]


def compute_filter_key(
    query: str,
    expanded_ids: Iterable[str] | None = None,
    tree_rev: int = 0,
) -> str:
    """Compute a deterministic stable cache key for filtering state.

    Args:
        query: The current search/filter query (normalized to lowercase).
        expanded_ids: Set or iterable of expanded folder IDs (sorted for stability).
        tree_rev: A revision counter that increments when the tree structure changes.

    Returns:
        A hex string that uniquely identifies this filtering state.
        Same inputs always produce the same output.
    """
    query_norm = (query or "").strip().lower()

    # Sort expanded_ids for deterministic ordering
    if expanded_ids is None:
        ids_sorted: list[str] = []
    else:
        ids_sorted = sorted(str(x) for x in expanded_ids)

    # Build a canonical string representation
    parts = [
        f"q={query_norm}",
        f"rev={tree_rev}",
        f"exp={','.join(ids_sorted)}",
    ]
    canonical = "|".join(parts)

    # Return a short hash for efficiency
    return hashlib.md5(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def slice_visible_rows(
    rows: Sequence[T],
    scroll_y: float,
    viewport_height: float,
    row_height: float,
    overscan: int = 3,
) -> SliceResult[T]:
    """Slice rows to only those visible in the viewport plus overscan.

    This enables efficient rendering by only processing rows that are
    actually visible, plus a small buffer for smooth scrolling.

    Args:
        rows: The full list of rows to slice.
        scroll_y: Current scroll offset in pixels (0 = top, positive = scrolled down).
        viewport_height: Height of the visible viewport in pixels.
        row_height: Height of each row in pixels.
        overscan: Number of extra rows to include above and below the viewport.

    Returns:
        SliceResult with (start_index, end_index, visible_rows).
        - start_index: Index of first row in the slice (for offset calculations).
        - end_index: Index one past the last row in the slice.
        - visible_rows: The actual row objects in the visible range.
    """
    if not rows or row_height <= 0 or viewport_height <= 0:
        return SliceResult(0, 0, [])

    total_count = len(rows)

    # Calculate first visible row (scroll_y / row_height)
    first_visible = int(scroll_y / row_height)

    # Calculate how many rows fit in viewport
    visible_count = int(viewport_height / row_height) + 1

    # Apply overscan
    start = max(0, first_visible - overscan)
    end = min(total_count, first_visible + visible_count + overscan)

    return SliceResult(start, end, list(rows[start:end]))


def estimate_total_height(row_count: int, row_height: float) -> float:
    """Estimate total scroll height for a list of rows.

    Args:
        row_count: Total number of rows in the list.
        row_height: Height of each row in pixels.

    Returns:
        Total height in pixels needed to display all rows.
    """
    if row_count <= 0 or row_height <= 0:
        return 0.0
    return float(row_count) * row_height
