"""Pure helpers for editor selection state.

Provides pure functions for extracting selection information from
controller state without mutating it.

Import-safe and headless-safe. Does not depend on arcade or runtime state.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SelectionState(Protocol):
    """Protocol for objects that have selection state.

    This allows the helpers to work with EditorModeController or any
    object that has the same selection attributes.
    """

    selected_entity: Any
    _selected_entity_ids: list[str]
    _primary_entity_id: str | None


def selected_entity_id(state: Any) -> str | None:
    """Get the ID of the currently selected (primary) entity.

    Tries multiple sources in order:
    1. _primary_entity_id attribute
    2. selected_entity.mesh_name attribute
    3. selected_entity.mesh_entity_data["id"]

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        The entity ID string, or None if no entity is selected.
    """
    # Try _primary_entity_id first
    primary_id = getattr(state, "_primary_entity_id", None)
    if primary_id and isinstance(primary_id, str):
        return str(primary_id)

    # Fallback to selected_entity
    selected = getattr(state, "selected_entity", None)
    if selected is None:
        return None

    # Try mesh_name
    mesh_name = getattr(selected, "mesh_name", None)
    if mesh_name and isinstance(mesh_name, str):
        return str(mesh_name)

    # Try mesh_entity_data["id"]
    entity_data = getattr(selected, "mesh_entity_data", None)
    if isinstance(entity_data, dict):
        eid = entity_data.get("id")
        if eid and isinstance(eid, str):
            return str(eid)

    return None


def is_entity_selected(state: Any) -> bool:
    """Check if any entity is currently selected.

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        True if an entity is selected, False otherwise.
    """
    return selected_entity_id(state) is not None


def is_multi_selected(state: Any) -> bool:
    """Check if multiple entities are selected.

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        True if more than one entity is selected, False otherwise.
    """
    ids = getattr(state, "_selected_entity_ids", None)
    if not isinstance(ids, list):
        return False
    return len(ids) > 1


def selected_entity_ids(state: Any) -> list[str]:
    """Get the list of all selected entity IDs.

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        List of entity ID strings. Empty list if none selected.
    """
    ids = getattr(state, "_selected_entity_ids", None)
    if not isinstance(ids, list):
        return []
    return list(ids)  # Return copy to prevent mutation


def selection_count(state: Any) -> int:
    """Get the number of selected entities.

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        Number of selected entities (0 if none).
    """
    ids = getattr(state, "_selected_entity_ids", None)
    if not isinstance(ids, list):
        # Fallback to checking single selection
        return 1 if is_entity_selected(state) else 0
    return len(ids)


def selection_summary(state: Any) -> dict[str, Any]:
    """Build a summary dict of current selection state.

    Useful for debugging, logging, or provider responses.

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        Dict with keys:
        - primary_id: str | None
        - selected_ids: list[str]
        - count: int
        - is_multi: bool
    """
    primary_id = selected_entity_id(state)
    ids = selected_entity_ids(state)

    return {
        "primary_id": primary_id,
        "selected_ids": ids,
        "count": len(ids) if ids else (1 if primary_id else 0),
        "is_multi": len(ids) > 1 if ids else False,
    }


def is_scene_selected(state: Any) -> bool:
    """Check if the scene (rather than an entity) is the selection target.

    This is true when no entity is selected but the editor is active.
    Useful for determining whether operations should target scene-level
    settings vs entity-level properties.

    Args:
        state: An object with selection state (e.g., EditorModeController).

    Returns:
        True if no entity is selected (scene is the implicit target).
    """
    return not is_entity_selected(state)
