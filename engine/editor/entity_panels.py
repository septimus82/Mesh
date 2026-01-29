"""Entity panels (Outliner + Inspector) helper functions.

This module provides pure functions for building outliner/inspector display
and filtering entity lists. State management remains in EditorModeController.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .state import (
    ENTITY_PANEL_FIELDS,
    ENTITY_PANEL_FOCUS_INSPECTOR,
    ENTITY_PANEL_FOCUS_OUTLINER,
)
from .prefab_palette_panel import normalize_entity_panel_tags

if TYPE_CHECKING:
    from engine.editor_prefab_variant_ops import DiffRow
    from engine.editor_entity_ops import EntitySummary
    from .components_model import InspectorComponent, InspectorField


def filter_entity_panels_items(
    items: List["EntitySummary"],
    filter_text: str,
) -> List["EntitySummary"]:
    """Filter entity list by search text.

    Args:
        items: List of entity summaries to filter.
        filter_text: Search text (case-insensitive substring match).

    Returns:
        Filtered list of entities matching the search text.
    """
    raw = str(filter_text or "").strip().lower()
    if not raw:
        return list(items)
    filtered: List["EntitySummary"] = []
    for item in items:
        hay = f"{item.id} {item.name} {item.type}".lower()
        if raw in hay:
            filtered.append(item)
    return filtered


def clamp_entity_panels_index(index: int, count: int) -> int:
    """Clamp selection index to valid range.

    Args:
        index: Current selection index.
        count: Total number of items.

    Returns:
        Clamped index in range [0, count-1] or -1 if count is 0.
    """
    if count == 0:
        return -1
    return max(0, min(index, count - 1))


def resolve_entity_panels_id(
    entity: Dict[str, Any],
    fallback_index: Optional[int] = None,
) -> str:
    """Resolve a unique ID for an entity from its data.

    Tries keys in order: id, entity_id, mesh_name, name.

    Args:
        entity: Entity data dictionary.
        fallback_index: Index to use as fallback ID.

    Returns:
        Resolved entity ID string.
    """
    for key in ("id", "entity_id"):
        raw = entity.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    mesh_name = entity.get("mesh_name")
    if isinstance(mesh_name, str) and mesh_name.strip():
        return mesh_name.strip()
    name = entity.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    if fallback_index is not None:
        return f"idx:{int(fallback_index)}"
    return "<unnamed>"


def build_outliner_lines(
    *,
    active: bool,
    focus: str,
    search_text: str,
    search_focused: bool,
    items: List["EntitySummary"],
    cursor_index: int,
    selected_id: Optional[str],
) -> List[str]:
    """Build display lines for the outliner panel.

    Args:
        active: Whether entity panels are active.
        focus: Current focus panel (ENTITY_PANEL_FOCUS_OUTLINER or INSPECTOR).
        search_text: Current search text.
        search_focused: Whether search input is focused.
        items: List of entity summaries (already filtered).
        cursor_index: Current cursor position in the list.
        selected_id: ID of the currently selected entity (if any).

    Returns:
        List of strings to display in the outliner panel.
    """
    if not active:
        return []

    title = "OUTLINER"
    if focus == ENTITY_PANEL_FOCUS_OUTLINER:
        title += " [focus]"
    lines = [title, "-------------"]

    from .panel_search_model import format_search_bar_text  # noqa: PLC0415

    lines.append(format_search_bar_text(search_text, search_focused))
    lines.append("-------------")

    if not items:
        lines.append("  (No entities)")
        return lines

    max_visible = 19
    start_idx = 0
    if cursor_index > max_visible / 2:
        start_idx = max(0, int(cursor_index - max_visible / 2))
    end_idx = min(len(items), start_idx + max_visible)

    for i in range(start_idx, end_idx):
        summary = items[i]
        is_cursor = i == cursor_index
        is_selected = selected_id is not None and summary.id == selected_id
        if is_cursor:
            prefix = "> "
        elif is_selected:
            prefix = "* "
        else:
            prefix = "  "
        label = summary.name or summary.id
        if summary.id and summary.id != summary.name:
            label = f"{summary.name} ({summary.id})"
        lines.append(f"{prefix}{label} [{summary.type}]")

    return lines


def build_inspector_lines(
    *,
    active: bool,
    focus: str,
    text_edit_active: bool,
    sprite_name: Optional[str],
    entity_data: Dict[str, Any],
    inspector_index: int,
    text_field: Optional[str],
    text_buffer: str,
    sprite: Any = None,
    prefab_label: Optional[str] = None,
    override_rows: Optional[List["DiffRow"]] = None,
) -> List[str]:
    """Build display lines for the inspector panel.

    Args:
        active: Whether entity panels are active.
        focus: Current focus panel.
        text_edit_active: Whether text editing is active.
        sprite_name: Display name of the selected sprite.
        entity_data: Entity data dictionary.
        inspector_index: Current inspector field index.
        text_field: Field currently being edited (if any).
        text_buffer: Current text edit buffer.
        sprite: The selected sprite (for position/rotation fallbacks).

    Returns:
        List of strings to display in the inspector panel.
    """
    if not active:
        return []

    title = "INSPECTOR"
    if focus == ENTITY_PANEL_FOCUS_INSPECTOR:
        title += " [focus]"
    lines = [title, "-------------"]

    if text_edit_active:
        lines.append("Editing: ENTER apply | ESC cancel")

    if sprite_name is None:
        lines.append("No selection")
        return lines

    lines.append(f"Selected: {sprite_name}")

    rows = override_rows or []
    field_count = len(ENTITY_PANEL_FIELDS)
    total_selectable = field_count + len(rows)
    clamped_index = max(0, min(inspector_index, total_selectable - 1)) if total_selectable else 0

    editing_field = text_field if text_edit_active else None
    selected_field_index: int | None = None
    selected_override_index: int | None = None
    if field_count and clamped_index < field_count:
        selected_field_index = clamped_index
    elif rows:
        selected_override_index = max(0, clamped_index - field_count)

    for idx, field in enumerate(ENTITY_PANEL_FIELDS):
        key = field["key"]
        kind = field["kind"]
        label = field["label"]
        prefix = "> " if idx == selected_field_index else "  "
        if editing_field == key:
            value_text = f"{text_buffer}_"
        else:
            value_text = format_entity_field_value(entity_data, sprite, key, kind)
        lines.append(f"{prefix}{label}: {value_text}")

    if prefab_label:
        lines.append(f"Prefab: {prefab_label}")
    if rows:
        lines.append("Overrides:")
        for idx, row in enumerate(rows):
            prefix = "> " if idx == selected_override_index else "  "
            base_text = _format_override_value(row.base_value)
            override_text = _format_override_value(row.override_value)
            suffix = " [Revert]" if idx == selected_override_index else ""
            lines.append(f"{prefix}{row.key}: {base_text} -> {override_text}{suffix}")
        lines.append("  [Revert All] (Shift+R)")
    elif prefab_label:
        lines.append("Overrides:")
        lines.append("  (None)")

    return lines


def format_entity_field_value(
    entity_data: Dict[str, Any],
    sprite: Any,
    key: str,
    kind: str,
) -> str:
    """Format an entity field value for display.

    Args:
        entity_data: Entity data dictionary.
        sprite: The sprite object (for position/rotation fallbacks).
        key: Field key name.
        kind: Field type (float, string, tags).

    Returns:
        Formatted value string.
    """
    if kind == "float":
        if key == "x":
            raw = entity_data.get("x", getattr(sprite, "center_x", 0.0) if sprite else 0.0)
        elif key == "y":
            raw = entity_data.get("y", getattr(sprite, "center_y", 0.0) if sprite else 0.0)
        elif key == "rotation_deg":
            raw = entity_data.get("rotation", getattr(sprite, "angle", 0.0) if sprite else 0.0)
        else:
            raw = entity_data.get(key, 0.0)
        try:
            value = float(raw)
        except Exception:  # noqa: BLE001
            value = 0.0
        if key == "rotation_deg":
            value = value % 360.0
        return f"{value:.1f}"
    if kind == "tags":
        tags = normalize_entity_panel_tags(entity_data.get("tags"))
        return ", ".join(tags) if tags else "-"
    if kind == "string":
        raw = entity_data.get(key)
        text = str(raw or "").strip()
        return text if text else "-"
    raw = entity_data.get(key)
    return str(raw) if raw is not None else "-"


def get_entity_numeric_value(
    entity_data: Dict[str, Any],
    sprite: Any,
    key: str,
) -> float:
    """Get the numeric value of an entity field.

    Args:
        entity_data: Entity data dictionary.
        sprite: The sprite object (for position/rotation fallbacks).
        key: Field key name.

    Returns:
        Numeric value of the field.
    """
    if key == "x":
        raw = entity_data.get("x", getattr(sprite, "center_x", 0.0) if sprite else 0.0)
    elif key == "y":
        raw = entity_data.get("y", getattr(sprite, "center_y", 0.0) if sprite else 0.0)
    elif key == "rotation_deg":
        raw = entity_data.get("rotation", getattr(sprite, "angle", 0.0) if sprite else 0.0)
    else:
        raw = entity_data.get(key, 0.0)
    try:
        value = float(raw)
    except Exception:  # noqa: BLE001
        value = 0.0
    if key == "rotation_deg":
        value = value % 360.0
    return value


def _format_override_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.1f}"
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, dict):
        import json  # noqa: PLC0415

        return json.dumps(value, sort_keys=True)
    if isinstance(value, list):
        return str(value)
    return str(value)


def compute_outliner_scroll_window(
    cursor_index: int,
    total_count: int,
    max_visible: int = 20,
) -> tuple[int, int]:
    """Compute the visible window range for scrolling.

    Args:
        cursor_index: Current cursor position.
        total_count: Total number of items.
        max_visible: Maximum number of visible items.

    Returns:
        Tuple of (start_index, end_index).
    """
    start_idx = 0
    if cursor_index > max_visible / 2:
        start_idx = max(0, int(cursor_index - max_visible / 2))
    end_idx = min(total_count, start_idx + max_visible)
    return start_idx, end_idx

# -----------------------------------------------------------------------------
# Component Inspector Lines (v1)
# -----------------------------------------------------------------------------

def _format_field_value(field: "InspectorField") -> str:
    """Format a field value for display."""
    from .components_model import InspectorField  # noqa: PLC0415
    
    value = field.value
    
    if field.kind == "float":
        if value is None:
            return "0.0"
        try:
            return f"{float(value):.1f}"  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(value)
    
    if field.kind == "int":
        if value is None:
            return "0"
        try:
            return str(int(str(value)))
        except (TypeError, ValueError):
            return str(value)
    
    if field.kind == "bool":
        return "Yes" if value else "No"
    
    if field.kind == "color":
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            r, g, b = value[0], value[1], value[2]
            a = value[3] if len(value) >= 4 else 255
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return str(value) if value else "#ffffffff"
    
    if field.kind == "asset":
        if value:
            # Show just the filename
            path_str = str(value)
            if "/" in path_str:
                return path_str.split("/")[-1]
            if "\\" in path_str:
                return path_str.split("\\")[-1]
            return path_str
        return "(none)"
    
    if field.kind == "enum":
        return str(value) if value else "(none)"
    
    if field.kind == "string":
        return str(value) if value else "(none)"
    
    return str(value) if value is not None else "-"


def build_component_inspector_lines(
    components: "tuple[InspectorComponent, ...]",
    selection_index: int,
    edit_state: Optional[Dict[str, Any]] = None,
    show_add_row: bool = True,
) -> List[str]:
    """Build display lines for the component inspector panel.
    
    Each component has a header line: "[Transform]" etc.
    Then indented field lines: "  X: 120.0"
    Optionally includes a final "[+ Add Component]" row.
    
    Args:
        components: Tuple of InspectorComponent from build_components()
        selection_index: Current selection index in the flattened list
        edit_state: Optional dict with text editing state:
            - "active": bool - whether text edit is active
            - "buffer": str - current text buffer
        show_add_row: Whether to show the "[+ Add Component]" row
        
    Returns:
        List of display lines, deterministic and ordered
    """
    from .components_model import InspectorComponent, InspectorField  # noqa: PLC0415
    
    lines: List[str] = []
    current_idx = 0
    
    is_editing = edit_state.get("active", False) if edit_state else False
    edit_buffer = edit_state.get("buffer", "") if edit_state else ""
    
    for comp in components:
        # Header line
        is_selected = current_idx == selection_index
        prefix = "> " if is_selected else "  "
        removable_marker = " [-]" if comp.removable else ""
        lines.append(f"{prefix}[{comp.title}]{removable_marker}")
        current_idx += 1
        
        # Field lines
        for field in comp.fields:
            is_selected = current_idx == selection_index
            prefix = "> " if is_selected else "  "
            
            # Format value
            if is_selected and is_editing:
                value_str = f"{edit_buffer}_"
            else:
                value_str = _format_field_value(field)
            
            # Add editability indicator
            edit_marker = "" if field.editable else " (ro)"
            
            lines.append(f"{prefix}  {field.label}: {value_str}{edit_marker}")
            current_idx += 1
    
    # Add component row
    if show_add_row:
        is_selected = current_idx == selection_index
        prefix = "> " if is_selected else "  "
        lines.append(f"{prefix}[+ Add Component]")
    
    return lines


def get_component_inspector_row_count(
    components: "tuple[InspectorComponent, ...]",
    include_add_row: bool = True,
) -> int:
    """Get total row count for component inspector.
    
    Args:
        components: Tuple of InspectorComponent
        include_add_row: Whether to include the add component row
        
    Returns:
        Total number of rows
    """
    count = 0
    for comp in components:
        count += 1  # Header
        count += len(comp.fields)
    if include_add_row:
        count += 1
    return count


def resolve_component_inspector_selection(
    components: "tuple[InspectorComponent, ...]",
    selection_index: int,
) -> Optional[Dict[str, Any]]:
    """Resolve what is selected at the given index.
    
    Args:
        components: Tuple of InspectorComponent
        selection_index: Current selection index
        
    Returns:
        Dict with selection info:
            - "type": "header" | "field" | "add_row"
            - "component_kind": ComponentKind (for header/field)
            - "field_key": str (for field)
            - "field": InspectorField (for field)
            - "removable": bool (for header)
        Or None if index is out of bounds
    """
    from .components_model import ComponentKind, InspectorComponent, InspectorField  # noqa: PLC0415
    
    current_idx = 0
    
    for comp in components:
        # Header row
        if current_idx == selection_index:
            return {
                "type": "header",
                "component_kind": comp.kind,
                "removable": comp.removable,
            }
        current_idx += 1
        
        # Field rows
        for field in comp.fields:
            if current_idx == selection_index:
                return {
                    "type": "field",
                    "component_kind": comp.kind,
                    "field_key": field.key,
                    "field": field,
                }
            current_idx += 1
    
    # Add row
    if current_idx == selection_index:
        return {"type": "add_row"}
    
    return None
