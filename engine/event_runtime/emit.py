from __future__ import annotations

from typing import Any

from engine.event_runtime.normalize import normalize_event_name, normalize_payload
from engine.events import MeshEvent


def emit_event(window: object, name: str, payload: dict[str, Any] | None = None) -> None:
    event_name = normalize_event_name(name)
    normalized_payload = normalize_payload(payload)
    event = MeshEvent(type=event_name, payload=normalized_payload)

    emitter = getattr(window, "emit_event", None)
    if callable(emitter):
        emitter(event)
        return

    bus = getattr(window, "event_bus", None)
    emit_event_method = getattr(bus, "emit_event", None) if bus is not None else None
    if callable(emit_event_method):
        emit_event_method(event)

