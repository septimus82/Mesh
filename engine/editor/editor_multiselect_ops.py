"""Editor multiselect operations.

Pure functions for managing multi-selection state in the editor.
Selected IDs are maintained as a deterministic list (stable ordering).
"""

from __future__ import annotations

from typing import List


def toggle_selection(selected_ids: List[str], clicked_id: str, shift: bool) -> List[str]:
    """Toggle or set selection based on shift modifier.

    Args:
        selected_ids: Current list of selected entity IDs (stable order).
        clicked_id: ID of the clicked entity.
        shift: Whether Shift key is held.

    Returns:
        New list of selected IDs (does not mutate input).
    """
    if not clicked_id:
        return list(selected_ids)

    if not shift:
        # No shift: single select (replace selection)
        return [clicked_id]

    # Shift: toggle membership
    result = list(selected_ids)
    if clicked_id in result:
        result.remove(clicked_id)
    else:
        result.append(clicked_id)
    return result


def select_single(clicked_id: str) -> List[str]:
    """Create a single-item selection.

    Args:
        clicked_id: ID of the clicked entity.

    Returns:
        List containing only the clicked ID, or empty if ID is empty.
    """
    if not clicked_id:
        return []
    return [clicked_id]


def get_primary_id(selected_ids: List[str], clicked_id: str) -> str | None:
    """Get the primary (anchor) entity ID for drag operations.

    The primary entity is the one being directly dragged. If clicked_id
    is in the selection, it becomes primary. Otherwise, returns the first
    selected ID.

    Args:
        selected_ids: Current list of selected entity IDs.
        clicked_id: ID of the entity being clicked/dragged.

    Returns:
        Primary entity ID, or None if selection is empty.
    """
    if not selected_ids:
        return None

    if clicked_id and clicked_id in selected_ids:
        return clicked_id

    return selected_ids[0]


def is_entity_selected(selected_ids: List[str], entity_id: str) -> bool:
    """Check if an entity is in the selection.

    Args:
        selected_ids: Current list of selected entity IDs.
        entity_id: ID to check.

    Returns:
        True if entity is selected.
    """
    return entity_id in selected_ids


def clear_selection() -> List[str]:
    """Return an empty selection list.

    Returns:
        Empty list.
    """
    return []
