"""
Pure dataclasses and functions for Component Inspector v1.

This module provides deterministic, side-effect-free functions for:
- Building inspector sections from entity JSON
- Managing section expand/collapse state
- Cursor navigation and clamping
- Applying edits to entity JSON fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Tuple


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

# Component section IDs and their display titles
COMPONENT_SECTIONS: List[Tuple[str, str]] = [
    ("transform", "Transform"),
    ("render", "Render"),
    ("interaction", "Interaction"),
    ("dialogue", "Dialogue"),
    ("light_source", "LightSource"),
]

# Field definitions per component section
# Each field: (key_path, label, field_kind, default_value)
# key_path supports dot notation for nested fields like "behaviour_config.LightSource.radius"
TRANSFORM_FIELDS: List[Tuple[str, str, str, Any]] = [
    ("x", "X", "float", 0.0),
    ("y", "Y", "float", 0.0),
    ("rotation", "Rotation", "float", 0.0),
    ("scale", "Scale", "float", 1.0),
]

RENDER_FIELDS: List[Tuple[str, str, str, Any]] = [
    ("sprite", "Sprite", "string", ""),
    ("layer", "Layer", "string", "entities"),
    ("render_layer", "Render Layer", "int", 0),
    ("depth_z", "Depth Z", "float", 0.0),
]

INTERACTION_FIELDS: List[Tuple[str, str, str, Any]] = [
    ("interact_label", "Interact Label", "string", ""),
    ("solid", "Solid", "bool", False),
]

DIALOGUE_FIELDS: List[Tuple[str, str, str, Any]] = [
    ("dialogue.speaker", "Speaker", "string", ""),
]

LIGHT_SOURCE_FIELDS: List[Tuple[str, str, str, Any]] = [
    ("behaviour_config.LightSource.radius", "Radius", "float", 320.0),
    ("behaviour_config.LightSource.color", "Color", "string", "#ffffff"),
    ("behaviour_config.LightSource.enabled", "Enabled", "bool", True),
    ("behaviour_config.LightSource.offset_x", "Offset X", "float", 0.0),
    ("behaviour_config.LightSource.offset_y", "Offset Y", "float", 0.0),
]

# Numeric adjustment steps
NUMERIC_STEP_NORMAL = 1.0
NUMERIC_STEP_SHIFT = 10.0


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ComponentRow:
    """A single row in a component section (header or field)."""

    kind: Literal["header", "field"]
    key: str  # For header: section_id, for field: field key path
    label: str
    value: Any  # Current value (for display), None for headers
    editable: bool
    field_kind: Literal["header", "float", "int", "string", "bool"]

    @staticmethod
    def header(section_id: str, title: str) -> "ComponentRow":
        """Create a header row for a section."""
        return ComponentRow(
            kind="header",
            key=section_id,
            label=title,
            value=None,
            editable=False,
            field_kind="header",
        )

    @staticmethod
    def field(
        key: str, label: str, value: Any, field_kind: str, editable: bool = True
    ) -> "ComponentRow":
        """Create a field row."""
        return ComponentRow(
            kind="field",
            key=key,
            label=label,
            value=value,
            editable=editable,
            field_kind=field_kind,  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class ComponentSection:
    """A collapsible component section with rows."""

    id: str
    title: str
    expanded: bool
    rows: Tuple[ComponentRow, ...]  # Immutable tuple of rows

    @property
    def visible_rows(self) -> Tuple[ComponentRow, ...]:
        """Return rows visible based on expanded state."""
        if self.expanded:
            return self.rows
        # When collapsed, only show the header row
        return tuple(r for r in self.rows if r.kind == "header")

    @property
    def header_row(self) -> Optional[ComponentRow]:
        """Return the header row if present."""
        for r in self.rows:
            if r.kind == "header":
                return r
        return None


@dataclass(frozen=True, slots=True)
class InspectorCursor:
    """Cursor position in the inspector."""

    section_id: str
    row_index: int  # Index within visible rows of the section

    @staticmethod
    def default() -> "InspectorCursor":
        """Return default cursor at first section header."""
        return InspectorCursor(section_id="transform", row_index=0)


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _get_nested_value(data: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """Get a nested value using dot notation (e.g., 'behaviour_config.LightSource.radius')."""
    parts = key_path.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return default
        current = current.get(part, default)
        if current is default:
            return default
    return current


def _set_nested_value(data: Dict[str, Any], key_path: str, value: Any) -> Dict[str, Any]:
    """Set a nested value using dot notation, returning a new dict."""
    result = dict(data)  # Shallow copy top level
    parts = key_path.split(".")

    if len(parts) == 1:
        result[parts[0]] = value
        return result

    # Navigate/create nested structure
    current = result
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        else:
            current[part] = dict(current[part])  # Copy nested dict
        current = current[part]

    current[parts[-1]] = value
    return result


def _has_behaviour(entity_json: Dict[str, Any], behaviour_name: str) -> bool:
    """Check if entity has a specific behaviour."""
    behaviours = entity_json.get("behaviours", [])
    if not behaviours:
        return False

    for b in behaviours:
        if isinstance(b, str) and b == behaviour_name:
            return True
        if isinstance(b, dict) and b.get("type") == behaviour_name:
            return True

    return False


def _has_dialogue(entity_json: Dict[str, Any]) -> bool:
    """Check if entity has dialogue configuration."""
    # Check legacy format
    if entity_json.get("dialogue"):
        return True
    # Check behaviour config format
    bc = entity_json.get("behaviour_config", {})
    if bc.get("Dialogue"):
        return True
    return _has_behaviour(entity_json, "Dialogue")


def _has_light_source(entity_json: Dict[str, Any]) -> bool:
    """Check if entity has LightSource behaviour."""
    bc = entity_json.get("behaviour_config", {})
    if bc.get("LightSource"):
        return True
    return _has_behaviour(entity_json, "LightSource")


def _section_applies_to_entity(section_id: str, entity_json: Dict[str, Any]) -> bool:
    """Determine if a section is relevant for the given entity."""
    if section_id == "transform":
        # Transform always applies
        return True
    if section_id == "render":
        # Render applies if entity has sprite
        return bool(entity_json.get("sprite"))
    if section_id == "interaction":
        # Interaction applies if entity has interaction fields
        return bool(
            entity_json.get("interact_label")
            or entity_json.get("tags")
            or entity_json.get("tag")
            or "solid" in entity_json
        )
    if section_id == "dialogue":
        return _has_dialogue(entity_json)
    if section_id == "light_source":
        return _has_light_source(entity_json)
    return False


def _get_fields_for_section(section_id: str) -> List[Tuple[str, str, str, Any]]:
    """Get field definitions for a section."""
    if section_id == "transform":
        return TRANSFORM_FIELDS
    if section_id == "render":
        return RENDER_FIELDS
    if section_id == "interaction":
        return INTERACTION_FIELDS
    if section_id == "dialogue":
        return DIALOGUE_FIELDS
    if section_id == "light_source":
        return LIGHT_SOURCE_FIELDS
    return []


def _build_section(
    section_id: str,
    title: str,
    entity_json: Dict[str, Any],
    expanded: bool,
) -> ComponentSection:
    """Build a single component section."""
    rows: List[ComponentRow] = []

    # Add header row
    rows.append(ComponentRow.header(section_id, title))

    # Add field rows
    field_defs = _get_fields_for_section(section_id)
    for key_path, label, field_kind, default in field_defs:
        value = _get_nested_value(entity_json, key_path, default)
        rows.append(ComponentRow.field(key_path, label, value, field_kind))

    return ComponentSection(
        id=section_id,
        title=title,
        expanded=expanded,
        rows=tuple(rows),
    )


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def build_inspector_sections(
    entity_json: Dict[str, Any],
    sprite: Optional[Any] = None,  # Optional sprite for additional context
    expanded_state: Optional[Dict[str, bool]] = None,
) -> List[ComponentSection]:
    """
    Build inspector sections for an entity.

    Args:
        entity_json: The entity's JSON data dict
        sprite: Optional sprite object (for future use)
        expanded_state: Dict mapping section_id -> expanded bool

    Returns:
        List of ComponentSection objects for sections relevant to this entity
    """
    if expanded_state is None:
        expanded_state = {}

    sections: List[ComponentSection] = []

    for section_id, title in COMPONENT_SECTIONS:
        if not _section_applies_to_entity(section_id, entity_json):
            continue

        expanded = expanded_state.get(section_id, True)  # Default expanded
        section = _build_section(section_id, title, entity_json, expanded)
        sections.append(section)

    return sections


def toggle_section(
    expanded_state: Dict[str, bool], section_id: str
) -> Dict[str, bool]:
    """
    Toggle a section's expanded state.

    Args:
        expanded_state: Current expanded state dict
        section_id: ID of section to toggle

    Returns:
        New expanded state dict (does not mutate input)
    """
    new_state = dict(expanded_state)
    current = new_state.get(section_id, True)
    new_state[section_id] = not current
    return new_state


def clamp_inspector_cursor(
    cursor: InspectorCursor, sections: List[ComponentSection]
) -> InspectorCursor:
    """
    Clamp cursor to valid position within sections.

    Args:
        cursor: Current cursor position
        sections: List of visible sections

    Returns:
        Clamped cursor (may be same object if already valid)
    """
    if not sections:
        return InspectorCursor.default()

    # Find the section
    section = None
    section_idx = 0
    for i, s in enumerate(sections):
        if s.id == cursor.section_id:
            section = s
            section_idx = i
            break

    # If section not found, clamp to first section
    if section is None:
        section = sections[0]
        return InspectorCursor(
            section_id=section.id,
            row_index=0,
        )

    # Clamp row index to visible rows
    visible = section.visible_rows
    if not visible:
        # Section has no visible rows, move to next section
        if section_idx + 1 < len(sections):
            next_section = sections[section_idx + 1]
            return InspectorCursor(section_id=next_section.id, row_index=0)
        # No next section, stay at first section
        return InspectorCursor(section_id=sections[0].id, row_index=0)

    clamped_row = max(0, min(cursor.row_index, len(visible) - 1))

    if clamped_row == cursor.row_index and section.id == cursor.section_id:
        return cursor

    return InspectorCursor(section_id=section.id, row_index=clamped_row)


def get_cursor_row(
    cursor: InspectorCursor, sections: List[ComponentSection]
) -> Optional[ComponentRow]:
    """Get the ComponentRow at the cursor position."""
    for section in sections:
        if section.id == cursor.section_id:
            visible = section.visible_rows
            if 0 <= cursor.row_index < len(visible):
                return visible[cursor.row_index]
    return None


def move_cursor(
    cursor: InspectorCursor,
    sections: List[ComponentSection],
    direction: Literal["up", "down"],
) -> InspectorCursor:
    """
    Move cursor up or down through visible rows.

    Args:
        cursor: Current cursor
        sections: List of sections
        direction: "up" or "down"

    Returns:
        New cursor position
    """
    if not sections:
        return cursor

    # Build flat list of (section_id, row_index) for all visible rows
    flat_positions: List[Tuple[str, int]] = []
    for section in sections:
        for i, _row in enumerate(section.visible_rows):
            flat_positions.append((section.id, i))

    if not flat_positions:
        return cursor

    # Find current position in flat list
    current_flat_idx = 0
    for i, (sid, ridx) in enumerate(flat_positions):
        if sid == cursor.section_id and ridx == cursor.row_index:
            current_flat_idx = i
            break

    # Move
    if direction == "up":
        new_flat_idx = max(0, current_flat_idx - 1)
    else:
        new_flat_idx = min(len(flat_positions) - 1, current_flat_idx + 1)

    new_section_id, new_row_idx = flat_positions[new_flat_idx]
    return InspectorCursor(section_id=new_section_id, row_index=new_row_idx)


def apply_inspector_edit(
    entity_json: Dict[str, Any],
    cursor: InspectorCursor,
    sections: List[ComponentSection],
    delta_or_text: Any,
    is_text_commit: bool = False,
) -> Tuple[Dict[str, Any], bool]:
    """
    Apply an edit to the entity JSON at the cursor position.

    Args:
        entity_json: Current entity JSON
        cursor: Current cursor position
        sections: Current sections (to find the field)
        delta_or_text: For numeric fields, a float delta; for string/text, the new text
        is_text_commit: True if this is a text field commit

    Returns:
        Tuple of (new_entity_json, changed: bool)
    """
    row = get_cursor_row(cursor, sections)
    if row is None or row.kind != "field" or not row.editable:
        return entity_json, False

    key_path = row.key
    current_value = _get_nested_value(entity_json, key_path)

    new_value: Any = None

    if row.field_kind == "float":
        if is_text_commit:
            # Parse text as float
            try:
                new_value = float(delta_or_text)
            except (ValueError, TypeError):
                return entity_json, False
        else:
            # Apply delta
            if current_value is None:
                current_value = 0.0
            new_value = float(current_value) + float(delta_or_text)

    elif row.field_kind == "int":
        if is_text_commit:
            try:
                new_value = int(delta_or_text)
            except (ValueError, TypeError):
                return entity_json, False
        else:
            if current_value is None:
                current_value = 0
            new_value = int(current_value) + int(delta_or_text)

    elif row.field_kind == "string":
        new_value = str(delta_or_text)

    elif row.field_kind == "bool":
        # Always toggle bool fields (Enter toggles)
        new_value = not bool(current_value)

    else:
        return entity_json, False

    # Check if actually changed
    if new_value == current_value:
        return entity_json, False

    # Apply the change
    new_entity_json = _set_nested_value(entity_json, key_path, new_value)
    return new_entity_json, True


def format_field_value(value: Any, field_kind: str) -> str:
    """Format a field value for display."""
    if value is None:
        return ""
    if field_kind == "float":
        if isinstance(value, float):
            # Show 1 decimal place for cleaner display
            return f"{value:.1f}"
        return str(value)
    if field_kind == "bool":
        return "Yes" if value else "No"
    return str(value)
