"""Pure gameplay event bus with stable ordering and replay-friendly design.

This module provides a deterministic event queue for gameplay events that
is separate from the engine's MeshEventBus. It provides:

- FIFO ordering with stable event IDs
- Replay-friendly design (events can be drained and re-queued)
- Optional inclusion in world digest for save determinism
- Schema validation for event payloads

Usage Example::

    bus = GameplayEventBus()
    
    # Emit events
    bus.emit("on_enter", zone="trigger_1", entity="Player")
    bus.emit("on_interact", entity="Player", target="NPC")
    
    # Process events
    for event in bus.drain():
        handle_event(event)
    
    # Check pending events
    pending = bus.peek()
    
    # Get deterministic digest for save verification
    digest = bus.digest()

Architecture:
    Events are stored as GameplayEvent dataclasses with monotonically increasing
    sequence numbers. The queue maintains insertion order and provides stable
    iteration during draining.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GameplayEvent:
    """Immutable gameplay event with sequence number for ordering.
    
    Attributes:
        event_type: The event type identifier (e.g., "on_enter", "on_interact").
        payload: Event-specific data as a dictionary.
        sequence: Monotonically increasing sequence number for ordering.
        source_entity: Optional ID of the entity that emitted the event.
        source_behaviour: Optional name of the behaviour that emitted the event.
    """

    event_type: str
    payload: dict[str, Any]
    sequence: int
    source_entity: str = ""
    source_behaviour: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "sequence": self.sequence,
            "source_entity": self.source_entity,
            "source_behaviour": self.source_behaviour,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameplayEvent":
        """Create from dictionary."""
        return cls(
            event_type=str(data.get("event_type", "")),
            payload=dict(data.get("payload") or {}),
            sequence=int(data.get("sequence", 0)),
            source_entity=str(data.get("source_entity", "")),
            source_behaviour=str(data.get("source_behaviour", "")),
        )


@dataclass
class GameplayEventBus:
    """Pure event bus with stable ordering and replay-friendly design.
    
    This event bus maintains a FIFO queue of gameplay events with deterministic
    ordering. Events are assigned monotonically increasing sequence numbers
    to ensure stable iteration order.
    
    Attributes:
        include_in_digest: Whether to include pending events in world digest.
    """

    include_in_digest: bool = True
    _queue: list[GameplayEvent] = field(default_factory=list)
    _next_sequence: int = field(default=0)
    _history: list[GameplayEvent] = field(default_factory=list)
    _history_limit: int = field(default=100)
    _entity_history: dict[str, list[GameplayEvent]] = field(default_factory=dict)
    _entity_history_limit: int = field(default=20)

    def emit(
        self,
        event_type: str,
        *,
        source_entity: str = "",
        source_behaviour: str = "",
        **payload: Any,
    ) -> GameplayEvent:
        """Emit a new gameplay event to the queue.
        
        Args:
            event_type: The event type identifier.
            source_entity: Optional ID of the emitting entity.
            source_behaviour: Optional name of the emitting behaviour.
            **payload: Event-specific data.
            
        Returns:
            The created GameplayEvent.
        """
        # Normalize payload for determinism
        normalized_payload = _normalize_payload(payload)

        event = GameplayEvent(
            event_type=str(event_type).strip(),
            payload=normalized_payload,
            sequence=self._next_sequence,
            source_entity=str(source_entity),
            source_behaviour=str(source_behaviour),
        )
        self._next_sequence += 1
        self._queue.append(event)
        return event

    def emit_event(self, event: GameplayEvent) -> None:
        """Re-emit an existing event (useful for replay).
        
        The event keeps its original sequence number.
        """
        self._queue.append(event)

    def drain(self) -> list[GameplayEvent]:
        """Remove and return all pending events in order.
        
        Returns:
            List of events in sequence order.
        """
        # Sort by sequence to ensure deterministic order
        events = sorted(self._queue, key=lambda e: e.sequence)
        self._queue.clear()

        # Add to history
        for event in events:
            self._history.append(event)
            # Also track per-entity history
            if event.source_entity:
                if event.source_entity not in self._entity_history:
                    self._entity_history[event.source_entity] = []
                entity_list = self._entity_history[event.source_entity]
                entity_list.append(event)
                while len(entity_list) > self._entity_history_limit:
                    entity_list.pop(0)
        while len(self._history) > self._history_limit:
            self._history.pop(0)

        return events

    def peek(self) -> list[GameplayEvent]:
        """Return pending events without removing them.
        
        Returns:
            Copy of pending events in sequence order.
        """
        return sorted(self._queue, key=lambda e: e.sequence)

    def clear(self) -> int:
        """Remove all pending events.
        
        Returns:
            Number of events removed.
        """
        count = len(self._queue)
        self._queue.clear()
        return count

    def pending_count(self) -> int:
        """Return the number of pending events."""
        return len(self._queue)

    def get_history(self, limit: int = 10) -> list[GameplayEvent]:
        """Return recent processed events.
        
        Args:
            limit: Maximum number of events to return.
            
        Returns:
            Most recent processed events.
        """
        return self._history[-limit:]

    def get_entity_history(self, entity_id: str, limit: int = 10) -> list[GameplayEvent]:
        """Return recent events for a specific entity.
        
        Args:
            entity_id: Entity ID to filter by.
            limit: Maximum number of events to return.
            
        Returns:
            Most recent events from the entity.
        """
        entity_list = self._entity_history.get(entity_id, [])
        return entity_list[-limit:]

    def get_event_log_summary(
        self,
        entity_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return event log summary for inspection.
        
        Args:
            entity_id: Optional entity ID to filter by.
            limit: Maximum number of events.
            
        Returns:
            List of event summary dicts.
        """
        if entity_id:
            events = self.get_entity_history(entity_id, limit)
        else:
            events = self.get_history(limit)

        return [
            {
                "seq": e.sequence,
                "type": e.event_type,
                "source": e.source_entity[:20] if e.source_entity else "",
                "behaviour": e.source_behaviour,
                "keys": list(e.payload.keys())[:5],
            }
            for e in events
        ]

    def set_history_limit(self, global_limit: int = 100, entity_limit: int = 20) -> None:
        """Configure history limits.
        
        Args:
            global_limit: Maximum events in global history.
            entity_limit: Maximum events per entity.
        """
        self._history_limit = max(1, int(global_limit))
        self._entity_history_limit = max(1, int(entity_limit))

        # Trim if needed
        while len(self._history) > self._history_limit:
            self._history.pop(0)
        for entity_list in self._entity_history.values():
            while len(entity_list) > self._entity_history_limit:
                entity_list.pop(0)

    def digest(self) -> str:
        """Compute a deterministic digest of pending events.
        
        This can be included in world state for save verification.
        
        Returns:
            SHA256 hex digest of pending event state.
        """
        if not self.include_in_digest:
            return ""

        # Sort by sequence for determinism
        events = sorted(self._queue, key=lambda e: e.sequence)

        # Build deterministic representation
        data = [e.to_dict() for e in events]
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()[:32]

    def saveable_state(self) -> dict[str, Any]:
        """Return state for serialization.
        
        Returns:
            Dictionary with queue state for saving.
        """
        events = sorted(self._queue, key=lambda e: e.sequence)
        return {
            "next_sequence": self._next_sequence,
            "pending_events": [e.to_dict() for e in events],
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore state from serialization.
        
        Args:
            state: Dictionary from saveable_state().
        """
        self._next_sequence = int(state.get("next_sequence", 0))
        self._queue.clear()

        pending = state.get("pending_events") or []
        for event_data in pending:
            if isinstance(event_data, dict):
                event = GameplayEvent.from_dict(event_data)
                self._queue.append(event)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize payload for deterministic serialization.
    
    Sorts keys and converts values to JSON-safe types.
    """
    result: dict[str, Any] = {}
    for key in sorted(payload.keys()):
        value = payload[key]
        result[str(key)] = _normalize_value(value)
    return result


def _normalize_value(value: Any) -> Any:
    """Normalize a single value for serialization."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    if isinstance(value, dict):
        return _normalize_payload(value)
    # Fallback to string
    return str(value)


# Validation errors for event configs
@dataclass(frozen=True, slots=True)
class EventConfigError:
    """Validation error for event configuration.
    
    Attributes:
        entity_id: ID of the entity with the error.
        behaviour_name: Name of the behaviour with the error.
        config_path: JSON path to the invalid config field.
        message: Human-readable error message.
        hint: Actionable fix suggestion.
    """

    entity_id: str
    behaviour_name: str
    config_path: str
    message: str
    hint: str = ""

    def __str__(self) -> str:
        base = f"[{self.entity_id}:{self.behaviour_name}] {self.config_path}: {self.message}"
        if self.hint:
            return f"{base} (hint: {self.hint})"
        return base


def validate_event_type(
    event_type: Any,
    *,
    entity_id: str = "",
    behaviour_name: str = "",
    config_path: str = "event_type",
) -> list[EventConfigError]:
    """Validate an event type string.
    
    Args:
        event_type: The event type to validate.
        entity_id: ID of the entity for error reporting.
        behaviour_name: Name of the behaviour for error reporting.
        config_path: JSON path for error reporting.
        
    Returns:
        List of validation errors (empty if valid).
    """
    errors: list[EventConfigError] = []

    if event_type is None:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=config_path,
            message="event_type is required",
        ))
        return errors

    if not isinstance(event_type, str):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=config_path,
            message=f"event_type must be a string, got {type(event_type).__name__}",
        ))
        return errors

    event_type = event_type.strip()
    if not event_type:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=config_path,
            message="event_type cannot be empty",
        ))
        return errors

    # Check for valid characters (alphanumeric, underscores)
    if not all(c.isalnum() or c == "_" for c in event_type):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=config_path,
            message="event_type must contain only alphanumeric characters and underscores",
        ))

    return errors
