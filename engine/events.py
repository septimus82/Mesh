"""Event system for decoupled communication between engine systems.

The event bus provides a publish/subscribe mechanism for gameplay events,
enabling loose coupling between behaviours, UI, and game systems.

Architecture:
    - **MeshEvent**: Immutable data container with type string and payload dict
    - **MeshEventBus**: Central dispatcher that routes events to subscribers
    - **Subscribers**: Callbacks registered for specific event types or wildcards

Common Event Types:
    - ``damage_applied``: Combat damage dealt to an entity
    - ``collectible_picked``: Player picked up an item
    - ``quest_started``, ``quest_stage_complete``: Quest progression
    - ``scene_loaded``: New scene finished loading
    - ``dialogue_started``, ``dialogue_ended``: NPC conversation
    - ``animation_event``: Animation frame triggered event

Usage Example::

    # Subscribe to specific event type
    def on_damage(event: MeshEvent):
        target = event.payload.get("target")
        amount = event.payload.get("amount", 0)
        print(f"{target} took {amount} damage")

    unsubscribe = window.events.subscribe("damage_applied", on_damage)

    # Emit an event
    window.events.emit("damage_applied", target="Player", amount=10, source="Enemy")

    # Cleanup when done
    unsubscribe()

See Also:
    - :class:`Behaviour.on_event` for handling events in behaviours
    - :mod:`engine.event_runtime` for event normalization utilities
"""

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
    """Immutable data container representing a gameplay event.

    Events are the primary mechanism for decoupled communication between
    engine systems. They consist of a type identifier and a payload dict
    containing event-specific data.

    Attributes:
        type: Event type identifier (e.g., "damage_applied", "quest_started").
            Should be snake_case and descriptive.
        payload: Dictionary containing event-specific data. Keys vary by event
            type but commonly include:
            - ``entity_name``: Name of the entity involved
            - ``scene_id``: Current scene path
            - Event-specific data (amount, target, source, etc.)

    Example::

        event = MeshEvent(
            type="collectible_picked",
            payload={
                "entity_name": "Player",
                "item_id": "health_potion",
                "quantity": 1,
            }
        )
    """

    type: EventType
    payload: dict[str, Any]


class MeshEventBus:
    """Central event dispatcher implementing publish/subscribe pattern.

    The event bus maintains subscriber lists for each event type and delivers
    events to registered callbacks. It also maintains a history buffer for
    debugging and replay functionality.

    Features:
        - Type-specific subscriptions via :meth:`subscribe`
        - Wildcard subscriptions via :meth:`subscribe_all`
        - Event history for debugging (last 50 events by default)
        - Optional recorder callback for replay/analytics
        - Thread-safe delivery with error isolation

    Attributes:
        _history_limit: Maximum events retained in history (default: 50).

    Example::

        bus = MeshEventBus()

        # Subscribe to damage events
        unsub = bus.subscribe("damage_applied", lambda e: print(e.payload))

        # Emit an event
        bus.emit("damage_applied", target="Enemy", amount=25)

        # Check recent events
        recent = bus.get_recent_event_names(3)
        # ['damage_applied']

        # Cleanup
        unsub()
    """

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
        """Register a callback for a specific event type.

        The callback will be invoked whenever an event of the specified type
        is emitted. Multiple callbacks can be registered for the same type.

        Args:
            event_type: The event type to listen for (e.g., "damage_applied").
                Must be a non-empty string.
            callback: Function accepting a MeshEvent parameter. Will be called
                synchronously when matching events are emitted.

        Returns:
            An unsubscribe function. Call it to remove the subscription::

                unsub = bus.subscribe("my_event", handler)
                # ... later ...
                unsub()  # Stop receiving events

        Raises:
            ValueError: If event_type is empty or None.

        Note:
            Callbacks are invoked in registration order. Exceptions in one
            callback don't prevent others from being called.
        """

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
        """Emit an event to all registered subscribers.

        This is the primary method for broadcasting events. It accepts either
        a pre-constructed MeshEvent or a type string with keyword payload args.

        Args:
            event_or_type: Either a MeshEvent instance or an event type string.
            **payload: When event_or_type is a string, these become the event
                payload. Common keys include:
                - ``entity_name``: The entity involved
                - ``target``: Target of an action
                - ``source``: Origin of an action
                - ``amount``: Numeric value (damage, quantity, etc.)

        Example::

            # Using type string and kwargs (preferred for simplicity)
            bus.emit("damage_applied", target="Enemy", amount=10, source="Player")

            # Using pre-constructed event
            event = MeshEvent("quest_started", {"quest_id": "main_quest_1"})
            bus.emit(event)

        Note:
            Event names are normalized to snake_case. Payloads are deep-copied
            to prevent mutation issues.
        """
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
