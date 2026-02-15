"""QuestHook behaviour - listens for events and updates quest counters.

Provides quest progress tracking by listening to gameplay events
and updating internal counters or triggering quest state changes.

Events emitted:
- quest_progress: When counter changes
- quest_step_completed: When a step threshold is reached

Save/restore:
- Tracks counters and triggered flags
- Fully deterministic on restore
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError, validate_event_type
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "QuestHook",
    description="Listens for events and updates quest counters/steps.",
    config_fields=[
        {
            "name": "quest_id",
            "description": "Quest identifier",
            "type": "string",
            "default": "",
        },
        {
            "name": "step_id",
            "description": "Step identifier within quest",
            "type": "string",
            "default": "",
        },
        {
            "name": "listen_events",
            "description": "Event types to listen for",
            "type": "array",
            "default": [],
        },
        {
            "name": "counter_name",
            "description": "Name of counter to track",
            "type": "string",
            "default": "count",
        },
        {
            "name": "target_count",
            "description": "Target count to complete step (-1 = no limit)",
            "type": "int",
            "default": 1,
        },
        {
            "name": "increment",
            "description": "Amount to increment counter per event",
            "type": "int",
            "default": 1,
        },
        {
            "name": "event_filter",
            "description": "Filter events by payload values (dict)",
            "type": "object",
            "default": {},
        },
        {
            "name": "one_shot",
            "description": "Only trigger once then ignore events",
            "type": "bool",
            "default": False,
        },
        {
            "name": "enabled",
            "description": "Whether the hook is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class QuestHookBehaviour(Behaviour):
    """Quest hook that listens for events and updates quest progress.
    
    Implements SaveableBehaviour for deterministic save/restore.
    All event processing is deterministic.
    """
    
    PARAM_DEFS = {
        "quest_id": ParamDef(str, "", "Quest identifier"),
        "step_id": ParamDef(str, "", "Step identifier"),
        "listen_events": ParamDef(list, [], "Event types to listen for"),
        "counter_name": ParamDef(str, "count", "Counter name"),
        "target_count": ParamDef(int, 1, "Target count for completion"),
        "increment": ParamDef(int, 1, "Increment per event"),
        "event_filter": ParamDef(dict, {}, "Event payload filter"),
        "one_shot": ParamDef(bool, False, "Trigger only once"),
        "enabled": ParamDef(bool, True, "Whether active"),
    }
    
    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__ (which calls setattr for params)
        self._enabled: bool = True
        self._counters: Dict[str, int] = {}
        self._triggered: bool = False
        self._completed: bool = False
        self._event_count: int = 0
        self._subscriptions: List[Any] = []
        
        super().__init__(entity, window, **config)
        
        # Config
        self.quest_id = str(self.config.get("quest_id", "")).strip()
        self.step_id = str(self.config.get("step_id", "")).strip()
        
        listen = self.config.get("listen_events", [])
        if isinstance(listen, str):
            listen = [listen]
        self.listen_events = set(str(e) for e in listen if e)
        
        self.counter_name = str(self.config.get("counter_name", "count"))
        self.target_count = int(self.config.get("target_count", 1))
        self.increment = int(self.config.get("increment", 1))
        self.event_filter = dict(self.config.get("event_filter", {}))
        self.one_shot = bool(self.config.get("one_shot", False))
        self._enabled = bool(self.config.get("enabled", True))
    
    @property
    def enabled(self) -> bool:
        """Whether the quest hook is active."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        was_enabled = self._enabled
        self._enabled = bool(value)
        if self._enabled and not was_enabled:
            self._subscribe()
        elif not self._enabled and was_enabled:
            self._unsubscribe()
    
    @property
    def is_completed(self) -> bool:
        """Whether target count has been reached."""
        return self._completed
    
    @property
    def current_count(self) -> int:
        """Current value of main counter."""
        return self._counters.get(self.counter_name, 0)
    
    @property
    def progress(self) -> float:
        """Progress toward completion (0.0 to 1.0)."""
        if self.target_count <= 0:
            return 1.0 if self._triggered else 0.0
        return min(1.0, self.current_count / self.target_count)
    
    def get_counter(self, name: Optional[str] = None) -> int:
        """Get a counter value."""
        return self._counters.get(name or self.counter_name, 0)
    
    def set_counter(self, value: int, name: Optional[str] = None) -> None:
        """Set a counter value (for external manipulation)."""
        self._counters[name or self.counter_name] = value
        self._check_completion()
    
    def reset(self) -> None:
        """Reset the hook to initial state."""
        self._counters = {}
        self._triggered = False
        self._completed = False
        self._event_count = 0
    
    def _subscribe(self) -> None:
        """Subscribe to gameplay events."""
        bus = getattr(self.window, "gameplay_event_bus", None)
        if bus is not None and hasattr(bus, "subscribe"):
            for event_type in self.listen_events:
                sub = bus.subscribe(event_type, self._on_event)
                self._subscriptions.append(sub)
    
    def _unsubscribe(self) -> None:
        """Unsubscribe from gameplay events."""
        for sub in self._subscriptions:
            if hasattr(sub, "cancel"):
                sub.cancel()
        self._subscriptions.clear()
    
    def _matches_filter(self, payload: Dict[str, Any]) -> bool:
        """Check if event payload matches the filter."""
        if not self.event_filter:
            return True
        
        for key, expected in self.event_filter.items():
            actual = payload.get(key)
            if actual != expected:
                return False
        return True
    
    def _emit_event(
        self,
        event_type: str,
        **kwargs,
    ) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")
        
        payload = {
            "quest_id": self.quest_id,
            "step_id": self.step_id,
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            **kwargs,
        }

        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="QuestHook",
        )
    
    def _check_completion(self) -> None:
        """Check if target count reached and emit completion if so."""
        if self._completed:
            return
        
        if self.target_count > 0 and self.current_count >= self.target_count:
            self._completed = True
            self._emit_event(
                "quest_step_completed",
                counter_name=self.counter_name,
                counter_value=self.current_count,
                target_count=self.target_count,
            )
    
    def _on_event(self, event) -> None:
        """Handle a received event (callback from bus subscription)."""
        if not self._enabled:
            return
        if self.one_shot and self._triggered:
            return
        
        # Get payload from event
        payload = {}
        if hasattr(event, "payload"):
            payload = dict(event.payload)
        elif isinstance(event, dict):
            payload = event
        
        self.handle_event(payload)
    
    def handle_event(self, payload: Dict[str, Any]) -> bool:
        """Handle an event and update counters.
        
        This method can be called directly for deterministic replay
        or via subscription callback.
        
        Args:
            payload: Event payload dict.
            
        Returns:
            True if event was processed.
        """
        if not self._enabled:
            return False
        if self.one_shot and self._triggered:
            return False
        
        # Check filter
        if not self._matches_filter(payload):
            return False
        
        # Update counter
        self._triggered = True
        self._event_count += 1
        old_count = self._counters.get(self.counter_name, 0)
        new_count = old_count + self.increment
        self._counters[self.counter_name] = new_count
        
        # Emit progress event
        self._emit_event(
            "quest_progress",
            counter_name=self.counter_name,
            old_value=old_count,
            new_value=new_count,
            increment=self.increment,
            event_count=self._event_count,
        )
        
        # Check for completion
        self._check_completion()
        
        return True
    
    def process_events(self, events: List[Dict[str, Any]]) -> int:
        """Process a batch of events deterministically.
        
        Used for replay or manual event injection.
        
        Args:
            events: List of event payloads to process.
            
        Returns:
            Number of events that matched and were processed.
        """
        processed = 0
        for evt in events:
            event_type = evt.get("event_type", "")
            if event_type in self.listen_events or not self.listen_events:
                if self.handle_event(evt):
                    processed += 1
        return processed
    
    # SaveableBehaviour protocol
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "enabled": self._enabled,
            "counters": dict(self._counters),
            "triggered": self._triggered,
            "completed": self._completed,
            "event_count": self._event_count,
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._enabled = bool(state.get("enabled", True))
        self._counters = dict(state.get("counters", {}))
        self._triggered = bool(state.get("triggered", False))
        self._completed = bool(state.get("completed", False))
        self._event_count = int(state.get("event_count", 0))
    
    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state summary for editor inspection."""
        return {
            "enabled": self._enabled,
            "quest_id": self.quest_id,
            "step_id": self.step_id,
            "counter_name": self.counter_name,
            "current_count": self.current_count,
            "target_count": self.target_count,
            "progress": round(self.progress, 2),
            "triggered": self._triggered,
            "completed": self._completed,
            "event_count": self._event_count,
            "listening_to": list(self.listen_events),
        }


def validate_quest_hook_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate QuestHook configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "QuestHook"
    
    # Validate quest_id
    quest_id = config.get("quest_id", "")
    if not quest_id or not str(quest_id).strip():
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="quest_id",
            message="quest_id is required",
        ))
    
    # Validate listen_events
    listen_events = config.get("listen_events", [])
    if isinstance(listen_events, str):
        listen_events = [listen_events]
    if not isinstance(listen_events, list):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="listen_events",
            message=f"listen_events must be a list, got {type(listen_events).__name__}",
        ))
    elif not listen_events:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="listen_events",
            message="listen_events must not be empty",
        ))
    else:
        for i, evt in enumerate(listen_events):
            if evt:
                errors.extend(validate_event_type(
                    str(evt),
                    entity_id=entity_id,
                    behaviour_name=behaviour_name,
                    config_path=f"listen_events[{i}]",
                ))
    
    # Validate target_count
    target_count = config.get("target_count", 1)
    try:
        target_count = int(target_count)
        if target_count == 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="target_count",
                message="target_count cannot be 0 (use -1 for no limit)",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="target_count",
            message=f"target_count must be an integer, got {type(target_count).__name__}",
        ))
    
    # Validate increment
    increment = config.get("increment", 1)
    try:
        increment = int(increment)
        if increment == 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="increment",
                message="increment cannot be 0",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="increment",
            message=f"increment must be an integer, got {type(increment).__name__}",
        ))
    
    # Validate event_filter
    event_filter = config.get("event_filter", {})
    if event_filter and not isinstance(event_filter, dict):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="event_filter",
            message=f"event_filter must be a dict, got {type(event_filter).__name__}",
        ))
    
    return errors
