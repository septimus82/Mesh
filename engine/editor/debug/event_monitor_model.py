"""Pure event monitor view models for editor tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from engine.editor.behaviour_inspector import EventLogRow, build_event_log_rows


@dataclass(frozen=True, slots=True)
class EventMonitorLine:
    text: str
    kind: str = ""
    source_entity: str | None = None
    filter_field: str | None = None


@dataclass(frozen=True, slots=True)
class EventLogViewModel:
    event_type_filter: str
    entity_id: str
    limit: int
    total_events: int
    rows: tuple[EventLogRow, ...]
    source_entities: tuple[str, ...]


def build_event_log_view_model(
    event_bus: Any,
    *,
    event_type_filter: str = "",
    entity_id: str = "",
    limit: int = 20,
) -> EventLogViewModel:
    """Build a filtered, deterministic event log view model."""
    norm_filter = _coerce_str(event_type_filter).lower()
    norm_entity = _coerce_str(entity_id)
    safe_limit = max(0, int(limit or 0))

    events: list[Any] = []
    if event_bus is not None:
        fetch_limit = max(1, max(safe_limit, 100))
        if norm_entity and hasattr(event_bus, "get_entity_history"):
            events = list(event_bus.get_entity_history(norm_entity, fetch_limit))
        elif hasattr(event_bus, "get_history"):
            events = list(event_bus.get_history(fetch_limit))

    events = [e for e in events if e is not None]
    events.sort(key=lambda e: int(getattr(e, "sequence", 0) or 0))
    total_events = len(events)

    filtered = []
    for event in events:
        if norm_entity:
            source_entity = _coerce_str(getattr(event, "source_entity", ""))
            if source_entity != norm_entity:
                continue
        if norm_filter:
            event_type = _coerce_str(getattr(event, "event_type", "")).lower()
            if norm_filter not in event_type:
                continue
        filtered.append(event)

    if safe_limit == 0:
        filtered = []
    elif len(filtered) > safe_limit:
        filtered = filtered[-safe_limit:]

    rows = build_event_log_rows(filtered, limit=len(filtered))
    source_entities = tuple(_coerce_str(getattr(event, "source_entity", "")) for event in filtered)

    return EventLogViewModel(
        event_type_filter=_coerce_str(event_type_filter),
        entity_id=norm_entity,
        limit=safe_limit,
        total_events=total_events,
        rows=tuple(rows),
        source_entities=source_entities,
    )


def build_event_log_view_model_from_settings(event_bus: Any, settings: Any | None) -> EventLogViewModel:
    """Build view model using filter settings from workspace settings."""
    event_type_filter = _coerce_str(getattr(settings, "debug_event_type_filter", "") if settings is not None else "")
    entity_id = _coerce_str(getattr(settings, "debug_event_entity_id", "") if settings is not None else "")
    raw_limit = getattr(settings, "debug_event_limit", 20) if settings is not None else 20
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = 20
    return build_event_log_view_model(
        event_bus,
        event_type_filter=event_type_filter,
        entity_id=entity_id,
        limit=limit,
    )


def build_event_monitor_entries(
    view_model: EventLogViewModel,
    *,
    active_filter_field: str | None = None,
) -> list[EventMonitorLine]:
    """Format event log view model as deterministic, metadata-rich lines."""
    entries: list[EventMonitorLine] = []
    entries.append(EventMonitorLine("Event Monitor", kind="header"))

    entries.extend(
        _build_filter_entries(
            view_model.event_type_filter,
            view_model.entity_id,
            view_model.limit,
            active_filter_field=active_filter_field,
        )
    )

    entries.append(
        EventMonitorLine(
            f"Events: {len(view_model.rows)}/{view_model.total_events}",
            kind="dim",
        )
    )

    if not view_model.rows:
        entries.append(EventMonitorLine("No events", kind="dim"))
        return entries

    for row, source_entity in zip(view_model.rows, view_model.source_entities):
        source = row.source_entity or "-"
        behaviour = row.source_behaviour or "-"
        payload = row.payload_preview or "(empty)"
        entries.append(
            EventMonitorLine(
                f"  #{row.sequence} {row.event_type} [{source}/{behaviour}] {payload}",
                kind="event",
                source_entity=source_entity or None,
            )
        )

    return entries


def build_event_monitor_lines(view_model: EventLogViewModel) -> list[str]:
    """Format event log view model as deterministic lines."""
    return [entry.text for entry in build_event_monitor_entries(view_model)]


def build_event_row_lines(view_model: EventLogViewModel) -> list[str]:
    """Format only the event rows as deterministic lines."""
    lines: list[str] = []
    for row, source_entity in zip(view_model.rows, view_model.source_entities):
        source = source_entity or row.source_entity or "-"
        behaviour = row.source_behaviour or "-"
        payload = row.payload_preview or "(empty)"
        lines.append(f"#{row.sequence} {row.event_type} [{source}/{behaviour}] {payload}")
    return lines


def format_event_rows_text(view_model: EventLogViewModel) -> str:
    """Format event rows as multi-line text for clipboard."""
    return "\n".join(build_event_row_lines(view_model))


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _build_filter_entries(
    event_type_filter: str,
    entity_id: str,
    limit: int,
    *,
    active_filter_field: str | None,
) -> list[EventMonitorLine]:
    return [
        _format_filter_entry(
            "Type Filter",
            event_type_filter,
            field="event_type",
            active_filter_field=active_filter_field,
            hint="Tab",
        ),
        _format_filter_entry(
            "Entity Filter",
            entity_id,
            field="entity_id",
            active_filter_field=active_filter_field,
        ),
        _format_filter_entry(
            "Limit",
            str(int(limit)),
            field="limit",
            active_filter_field=active_filter_field,
        ),
    ]


def _format_filter_entry(
    label: str,
    value: str,
    *,
    field: str,
    active_filter_field: str | None,
    hint: str | None = None,
) -> EventMonitorLine:
    active = field == active_filter_field
    hint_text = f" ({hint})" if hint else ""
    display_value = _format_filter_value(value, active=active)
    return EventMonitorLine(
        f"{label}{hint_text}: {display_value}",
        kind="filter_active" if active else "filter",
        filter_field=field,
    )


def _format_filter_value(value: str, *, active: bool) -> str:
    text = _coerce_str(value)
    if text:
        return f"{text}|" if active else text
    return "|" if active else "(any)"
