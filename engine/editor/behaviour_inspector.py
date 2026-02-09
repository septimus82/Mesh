"""Behaviour state inspector - exposes behaviour state for editor inspection.

Provides read-only summaries of behaviour internal state for debugging
and development purposes. Uses the get_inspector_state() method on behaviours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True, slots=True)
class BehaviourInspectorRow:
    """A single row in the behaviour inspector."""
    
    kind: str  # "header", "field", "separator"
    key: str
    label: str
    value: Any = None
    value_type: str = "string"


@dataclass(frozen=True, slots=True)
class BehaviourInspectorSection:
    """A section showing one behaviour's state."""
    
    behaviour_name: str
    behaviour_type: str
    entity_id: str
    rows: Tuple[BehaviourInspectorRow, ...] = ()
    is_expanded: bool = True


def get_behaviour_inspector_state(behaviour) -> Optional[Dict[str, Any]]:
    """Get inspector state from a behaviour if available.
    
    Args:
        behaviour: Behaviour instance to inspect.
        
    Returns:
        Inspector state dict or None if not available.
    """
    if hasattr(behaviour, "get_inspector_state"):
        try:
            result = behaviour.get_inspector_state()
            if isinstance(result, dict):
                return result
            return None
        except Exception:
            return None
    return None


def format_value_for_display(value: Any) -> Tuple[str, str]:
    """Format a value for display in inspector.
    
    Args:
        value: Value to format.
        
    Returns:
        Tuple of (formatted_string, value_type).
    """
    if value is None:
        return "None", "null"
    elif isinstance(value, bool):
        return str(value).lower(), "bool"
    elif isinstance(value, int):
        return str(value), "int"
    elif isinstance(value, float):
        return f"{value:.2f}", "float"
    elif isinstance(value, str):
        if len(value) > 50:
            return value[:47] + "...", "string"
        return value, "string"
    elif isinstance(value, (list, tuple)):
        return f"[{len(value)} items]", "array"
    elif isinstance(value, dict):
        return f"{{{len(value)} keys}}", "object"
    else:
        return str(value)[:50], "unknown"


def build_behaviour_inspector_rows(
    state: Dict[str, Any],
) -> List[BehaviourInspectorRow]:
    """Build inspector rows from behaviour state.
    
    Args:
        state: State dict from get_inspector_state().
        
    Returns:
        List of inspector rows.
    """
    rows = []
    
    # Sort keys for consistent display
    for key in sorted(state.keys()):
        value = state[key]
        formatted, value_type = format_value_for_display(value)
        
        rows.append(BehaviourInspectorRow(
            kind="field",
            key=key,
            label=key.replace("_", " ").title(),
            value=formatted,
            value_type=value_type,
        ))
    
    return rows


def build_behaviour_inspector_section(
    behaviour,
    entity_id: str = "",
    is_expanded: bool = True,
) -> Optional[BehaviourInspectorSection]:
    """Build an inspector section for a behaviour.
    
    Args:
        behaviour: Behaviour instance to inspect.
        entity_id: Entity ID for the section.
        is_expanded: Whether section is expanded.
        
    Returns:
        Inspector section or None if behaviour doesn't support inspection.
    """
    state = get_behaviour_inspector_state(behaviour)
    if state is None:
        return None
    
    # Get behaviour type name
    behaviour_type = type(behaviour).__name__
    
    # Get behaviour name from config or type
    behaviour_name = behaviour_type
    if hasattr(behaviour, "config") and isinstance(behaviour.config, dict):
        behaviour_name = behaviour.config.get("name", behaviour_type)
    
    rows = build_behaviour_inspector_rows(state)
    
    return BehaviourInspectorSection(
        behaviour_name=behaviour_name,
        behaviour_type=behaviour_type,
        entity_id=entity_id,
        rows=tuple(rows),
        is_expanded=is_expanded,
    )


def build_entity_behaviour_summary(
    entity,
    expand_states: Optional[Dict[str, bool]] = None,
) -> List[BehaviourInspectorSection]:
    """Build inspector sections for all behaviours on an entity.
    
    Args:
        entity: Entity with behaviours to inspect.
        expand_states: Optional dict of behaviour_type -> is_expanded.
        
    Returns:
        List of inspector sections for all inspectable behaviours.
    """
    sections = []
    expand_states = expand_states or {}
    
    # Get behaviours from entity
    behaviours = []
    if hasattr(entity, "behaviours"):
        behaviours = entity.behaviours
    elif hasattr(entity, "_behaviours"):
        behaviours = entity._behaviours
    
    entity_id = getattr(entity, "mesh_id", "")
    
    for behaviour in behaviours:
        behaviour_type = type(behaviour).__name__
        is_expanded = expand_states.get(behaviour_type, True)
        
        section = build_behaviour_inspector_section(
            behaviour,
            entity_id=entity_id,
            is_expanded=is_expanded,
        )
        
        if section is not None:
            sections.append(section)
    
    return sections


def format_behaviour_summary_text(
    sections: List[BehaviourInspectorSection],
) -> str:
    """Format behaviour sections as plain text for debugging.
    
    Args:
        sections: List of inspector sections.
        
    Returns:
        Formatted text string.
    """
    lines = []
    
    for section in sections:
        lines.append(f"[{section.behaviour_type}]")
        
        if section.is_expanded:
            for row in section.rows:
                if row.kind == "field":
                    lines.append(f"  {row.label}: {row.value}")
        
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# Event Log Inspector
# =============================================================================

@dataclass(frozen=True, slots=True)
class EventLogRow:
    """A single row in the event log."""
    
    sequence: int
    event_type: str
    source_entity: str
    source_behaviour: str
    payload_preview: str


@dataclass(frozen=True, slots=True)
class EventLogSection:
    """Event log inspector section."""
    
    title: str
    entity_id: str  # Empty for global log
    rows: Tuple[EventLogRow, ...] = ()
    is_expanded: bool = True


def build_event_log_rows(
    events: List[Any],
    limit: int = 10,
) -> List[EventLogRow]:
    """Build event log rows from event list.
    
    Args:
        events: List of GameplayEvent objects.
        limit: Maximum rows to return.
        
    Returns:
        List of event log rows.
    """
    rows = []
    
    for event in events[-limit:]:
        # Build payload preview
        payload_keys = list(event.payload.keys())[:3]
        if payload_keys:
            payload_preview = ", ".join(payload_keys)
            if len(event.payload) > 3:
                payload_preview += f" (+{len(event.payload) - 3})"
        else:
            payload_preview = "(empty)"
        
        rows.append(EventLogRow(
            sequence=event.sequence,
            event_type=event.event_type,
            source_entity=event.source_entity[:16] if event.source_entity else "",
            source_behaviour=event.source_behaviour,
            payload_preview=payload_preview,
        ))
    
    return rows


def build_event_log_section(
    event_bus,
    entity_id: str = "",
    limit: int = 10,
    is_expanded: bool = True,
) -> Optional[EventLogSection]:
    """Build event log inspector section.
    
    Args:
        event_bus: GameplayEventBus instance.
        entity_id: Entity ID for entity-specific log (empty for global).
        limit: Maximum events to show.
        is_expanded: Whether section is expanded.
        
    Returns:
        Event log section or None if no events.
    """
    if event_bus is None:
        return None
    
    if entity_id:
        if hasattr(event_bus, "get_entity_history"):
            events = event_bus.get_entity_history(entity_id, limit)
        else:
            return None
        title = f"Events ({entity_id[:16]})"
    else:
        if hasattr(event_bus, "get_history"):
            events = event_bus.get_history(limit)
        else:
            return None
        title = "Event Log (Global)"
    
    if not events:
        return None
    
    rows = build_event_log_rows(events, limit)
    
    return EventLogSection(
        title=title,
        entity_id=entity_id,
        rows=tuple(rows),
        is_expanded=is_expanded,
    )


def format_event_log_text(
    section: EventLogSection,
) -> str:
    """Format event log section as plain text.
    
    Args:
        section: Event log section.
        
    Returns:
        Formatted text string.
    """
    lines = [f"[{section.title}]"]
    
    if section.is_expanded:
        for row in section.rows:
            src = f"{row.source_entity}:{row.source_behaviour}" if row.source_entity else row.source_behaviour
            lines.append(f"  #{row.sequence} {row.event_type} <- {src}")
            lines.append(f"       {row.payload_preview}")
    
    return "\n".join(lines)
