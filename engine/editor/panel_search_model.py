"""Pure helpers for editor panel search bars."""

from __future__ import annotations


def format_search_bar_text(text: str, focused: bool) -> str:
    """Format a search bar label for panel headers."""
    value = str(text or "")
    if value:
        cursor = "|" if focused else ""
        return f"Search: {value}{cursor}"
    if focused:
        return "Search: |"
    return "Search: (Ctrl+F)"
