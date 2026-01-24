"""Event definitions for Mesh Engine."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from .logging_tools import get_logger

EventType = str
EventCallback = Callable[["MeshEvent"], None]

logger = get_logger(__name__)


@dataclass
class MeshEvent:
    """Simple data container that describes gameplay events."""

    type: EventType
    payload: dict[str, Any]


class MeshEventBus:
    """Lightweight publish/subscribe helper for Mesh events."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventCallback]] = {}
        self._wildcard_subscribers: List[EventCallback] = []
        self._history: List[Dict[str, Any]] = []
        self._history_limit: int = 50
        self._recorder: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_recorder(self, recorder: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """Set a callback to record all emitted events."""
        self._recorder = recorder

    def get_recent_events(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get the most recent events as structured dicts."""
        return self._history[-limit:]

    def get_recent_event_names(self, limit: int = 5) -> List[str]:
        """Get the names of the most recent events."""
        return [e["name"] for e in self._history[-limit:]]

    def subscribe(self, event_type: str, callback: EventCallback) -> Callable[[], None]:
        """Register a callback for a specific event type."""

        key = str(event_type or "").strip()
        if not key:
            raise ValueError("event_type must be a non-empty string")
        bucket = self._subscribers.setdefault(key, [])
        bucket.append(callback)

        def unsubscribe() -> None:
            listeners = self._subscribers.get(key)
            if not listeners:
                return
            try:
                listeners.remove(callback)
            except ValueError:
                return
            if not listeners:
                self._subscribers.pop(key, None)

        return unsubscribe

    def subscribe_all(self, callback: EventCallback) -> Callable[[], None]:
        """Register a wildcard callback invoked for all events."""

        self._wildcard_subscribers.append(callback)

        def unsubscribe() -> None:
            try:
                self._wildcard_subscribers.remove(callback)
            except ValueError:
                return

        return unsubscribe

    def emit(self, event_or_type: str | MeshEvent, **payload: Any) -> None:
        """Emit a MeshEvent. Can pass a MeshEvent object or a type string and payload."""
        if isinstance(event_or_type, MeshEvent):
            self.emit_event(event_or_type)
        else:
            from .event_runtime.normalize import normalize_event_name, normalize_payload

            event = MeshEvent(
                type=normalize_event_name(str(event_or_type)),
                payload=normalize_payload(dict(payload)),
            )
            self.emit_event(event)

    def emit_event(self, event: MeshEvent) -> None:
        """Deliver an already constructed MeshEvent to subscribers."""
        if event is None:
            return

        # Construct structured dict
        event_dict = {
            "name": event.type,
            "payload": event.payload,
            "timestamp": time.time(),
            "scene_id": event.payload.get("scene_id"),
            "entity_name": event.payload.get("entity_name") or event.payload.get("name"),
        }

        # Add to history
        self._history.append(event_dict)
        if len(self._history) > self._history_limit:
            self._history.pop(0)

        # Recorder
        if self._recorder:
            try:
                self._recorder(event_dict)
            except Exception as e:
                logger.error("[MeshEventBus] Recorder error: %s", e)

        listeners = list(self._subscribers.get(event.type, []))
        wildcard_listeners = list(self._wildcard_subscribers)

        for callback in listeners + wildcard_listeners:
            try:
                callback(event)
            except Exception as exc:  # noqa: BLE001 - best-effort logging only
                logger.error(
                    "[Mesh][EventBus] ERROR delivering '%s' to %s: %s",
                    event.type,
                    callback,
                    exc,
                )

    def get_subscriber_snapshot(self) -> dict[str, Any]:
        """Return a summary of subscriber counts for introspection."""

        return {
            "types": {event_type: len(listeners) for event_type, listeners in self._subscribers.items()},
            "wildcard": len(self._wildcard_subscribers),
        }

    def clear(self) -> None:
        """Remove all registered subscribers."""

        self._subscribers.clear()
        self._wildcard_subscribers.clear()
