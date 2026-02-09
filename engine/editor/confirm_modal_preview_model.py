"""
Pure logic model for the Confirm Modal Preview.
Handles text formatting, details toggling, and truncation suitable for the UI overlay.
"""
from typing import List, Tuple

def toggle_details(current_expanded: bool) -> bool:
    """Toggle expanded state."""
    return not current_expanded

def truncate_preview(lines: List[str], max_lines: int, expanded: bool) -> Tuple[List[str], int]:
    """
    Truncate preview lines if they exceed max_lines and not expanded.
    
    Args:
        lines: Full list of lines.
        max_lines: Maximum visible lines before truncation.
        expanded: If True, show all lines.
        
    Returns:
        (visible_lines, hidden_count)
    """
    total = len(lines)
    if expanded or total <= max_lines:
        return lines, 0
    
    # Reserve space for the "... (+X more)" line
    limit = max(1, max_lines - 1)
    visible = lines[:limit]
    hidden = total - limit
    
    return visible, hidden
