"""Gameplay event emission helper with legacy fallback.

This module centralizes gameplay event emission policy:
- Prefer ``gameplay_event_bus`` when available.
- Fall back to ``event_bus`` for legacy compatibility.
- Preserve payloads as-is (no timestamp or host metadata injection).
"""

from __future__ import annotations

from typing import Any


def _explicit_attr(ctx: Any, name: str) -> Any:
    """Read only explicitly-defined attributes (avoids MagicMock auto attrs)."""
    try:
        return object.__getattribute__(ctx, name)
    except Exception:
        return None


def emit_gameplay_event(
    ctx: Any,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    source_entity_id: str | None = None,
    source_behaviour: str = "",
) -> Any:
    """Emit a gameplay event via gameplay bus with legacy fallback.

    Args:
        ctx: Window/context object, or a bus-like object with ``emit``.
        event_type: Event type to emit.
        payload: Event payload dictionary.
        source_entity_id: Source entity identifier for gameplay bus events.
        source_behaviour: Source behaviour name for gameplay bus events.
    """
    if ctx is None:
        return None

    event_payload = dict(payload or {})
    gameplay_bus = _explicit_attr(ctx, "gameplay_event_bus")
    if gameplay_bus is not None and hasattr(gameplay_bus, "emit"):
        gameplay_payload = dict(event_payload)
        gameplay_payload.pop("source_entity", None)
        gameplay_payload.pop("source_behaviour", None)
        return gameplay_bus.emit(
            event_type,
            source_entity=str(source_entity_id or ""),
            source_behaviour=str(source_behaviour or ""),
            **gameplay_payload,
        )

    legacy_bus = _explicit_attr(ctx, "event_bus")
    if legacy_bus is not None and hasattr(legacy_bus, "emit"):
        return legacy_bus.emit(event_type, **event_payload)

    if hasattr(ctx, "emit"):
        emit_fn = getattr(ctx, "emit")
        emit_payload = dict(event_payload)
        emit_payload.pop("source_entity", None)
        emit_payload.pop("source_behaviour", None)
        try:
            return emit_fn(
                event_type,
                source_entity=str(source_entity_id or ""),
                source_behaviour=str(source_behaviour or ""),
                **emit_payload,
            )
        except TypeError:
            return emit_fn(event_type, **event_payload)

    return None
