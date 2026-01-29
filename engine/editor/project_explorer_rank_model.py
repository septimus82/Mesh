"""Deterministic ranking helpers for Project Explorer search results.

Provides fuzzy-ish ranking when filtering project rows by query:
- Exact filename match: highest priority
- Prefix match: high priority  
- Word boundary match: medium priority
- Substring match: lower priority

When query is empty, no ranking is applied (preserves tree order).
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

__all__ = [
    "normalize_query",
    "compute_match_score",
    "rank_rows",
    "SCORE_EXACT",
    "SCORE_PREFIX",
    "SCORE_WORD_BOUNDARY",
    "SCORE_SUBSTRING",
    "SCORE_NO_MATCH",
]

# Score constants (higher = better match)
SCORE_EXACT = 1000
SCORE_PREFIX = 600
SCORE_WORD_BOUNDARY = 400
SCORE_SUBSTRING = 200
SCORE_NO_MATCH = -1

T = TypeVar("T")


def normalize_query(q: str) -> str:
    """Normalize a search query for matching.

    - Strips whitespace
    - Converts to lowercase (casefold)
    - Returns empty string for None/whitespace-only

    Deterministic: same input always produces same output.
    """
    if not q:
        return ""
    return q.strip().casefold()


def compute_match_score(text: str, q: str) -> int:
    """Compute a match score for text against normalized query.

    Args:
        text: The text to match against (e.g., filename or path).
        q: The normalized query (should be result of normalize_query).

    Returns:
        Score value (higher = better match):
        - SCORE_EXACT (1000): Exact filename match
        - SCORE_PREFIX (600): Text starts with query
        - SCORE_WORD_BOUNDARY (400): Query appears after word boundary
        - SCORE_SUBSTRING (200): Query appears anywhere in text
        - SCORE_NO_MATCH (-1): No match

    Deterministic: same inputs always produce same output.
    """
    if not q:
        return SCORE_NO_MATCH

    text_lower = text.casefold() if text else ""
    if not text_lower:
        return SCORE_NO_MATCH

    # Extract filename from path for exact/prefix matching
    filename = text_lower.rsplit("/", 1)[-1]
    filename = filename.rsplit("\\", 1)[-1]

    # Check for exact filename match
    if filename == q:
        return SCORE_EXACT

    # Check for prefix match on filename
    if filename.startswith(q):
        return SCORE_PREFIX

    # Check for word boundary match (after _, -, ., or path separator)
    # Look for query appearing after a word boundary character
    word_boundaries = ("_", "-", ".", "/", "\\")
    for sep in word_boundaries:
        idx = text_lower.find(sep + q)
        if idx >= 0:
            return SCORE_WORD_BOUNDARY

    # Check for simple substring match anywhere in text
    if q in text_lower:
        return SCORE_SUBSTRING

    return SCORE_NO_MATCH


def rank_rows(
    rows: Sequence[T],
    q: str,
    get_text_fn: Callable[[T], str],
) -> list[T]:
    """Rank rows by relevance to query with deterministic tie-breakers.

    Args:
        rows: Sequence of rows to rank.
        q: The search query (will be normalized).
        get_text_fn: Function to extract searchable text from a row.

    Returns:
        List of rows sorted by:
        1. Score descending (best matches first)
        2. Shorter text first (tie-breaker)
        3. Lexicographic text (final tie-breaker)

    If query is empty, returns rows in original order.
    Deterministic: same inputs always produce same output.
    """
    q_norm = normalize_query(q)
    if not q_norm:
        return list(rows)

    # Build (row, text, score) tuples
    scored: list[tuple[T, str, int]] = []
    for row in rows:
        text = get_text_fn(row)
        score = compute_match_score(text, q_norm)
        if score > SCORE_NO_MATCH:
            scored.append((row, text, score))

    # Sort with deterministic tie-breakers:
    # 1. Score descending (negate for ascending sort)
    # 2. Text length ascending (shorter first)
    # 3. Text lexicographic ascending
    scored.sort(key=lambda x: (-x[2], len(x[1]), x[1].casefold()))

    return [item[0] for item in scored]
