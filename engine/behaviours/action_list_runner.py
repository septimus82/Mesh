"""ActionListRunner behaviour - composable action lists triggered by events.

Provides a reusable way to compose gameplay logic without writing new behaviours.
Listens for configured events and executes an ordered list of actions.

Supported actions:
- emit_event: Emit a gameplay event
- set_flag / clear_flag: Modify game state flags
- add_tag / remove_tag: Modify entity tags
- start_timer / stop_timer: Control timer behaviours
- start_dialogue: Trigger dialogue runner

Events emitted:
- action_list_started: When action list begins execution
- action_list_completed: When all actions finish

Save/restore:
- Tracks pending actions, last_triggered timestamp, run_count
- Fully deterministic on restore
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError, validate_event_type
from ..state_runtime import flags as state_flags
from .base import Behaviour, ParamDef
from .registry import register_behaviour


# =============================================================================
# Action Type Registry
# =============================================================================

VALID_ACTION_TYPES = frozenset({
    "emit_event",
    "set_flag",
    "clear_flag",
    "add_tag",
    "remove_tag",
    "start_timer",
    "stop_timer",
    "start_dialogue",
    "delay",  # Insert delay before next action
})

FLAG_ID_PATTERN = re.compile(r"^[a-z0-9_]+(?:\\.[a-z0-9_]+)*$")
FLAG_ID_PATTERN_TEXT = r"^[a-z0-9_]+(?:\\.[a-z0-9_]+)*$"


# =============================================================================
# ActionListRunner Behaviour
# =============================================================================

@register_behaviour(
    "ActionListRunner",
    description="Runs an ordered list of actions when triggered by events.",
    config_fields=[
        {
            "name": "listen_events",
            "description": "Event types to listen for",
            "type": "array",
            "default": [],
        },
        {
            "name": "event_filter",
            "description": "Filter events by payload values (dict)",
            "type": "object",
            "default": {},
        },
        {
            "name": "actions",
            "description": "Ordered list of action configs",
            "type": "array",
            "default": [],
        },
        {
            "name": "run_once",
            "description": "Only run actions once (ignore subsequent triggers)",
            "type": "bool",
            "default": False,
        },
        {
            "name": "cooldown",
            "description": "Minimum time between runs (0 = no cooldown)",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "enabled",
            "description": "Whether the runner is active",
            "type": "bool",
            "default": True,
        },
        {
            "name": "require_flags",
            "description": "Flags that must be true to trigger",
            "type": "array",
            "default": [],
        },
        {
            "name": "forbid_flags",
            "description": "Flags that must be false to trigger",
            "type": "array",
            "default": [],
        },
    ],
)
class ActionListRunnerBehaviour(Behaviour):
    """Runs an ordered list of actions when triggered by events.
    
    Implements SaveableBehaviour for deterministic save/restore.
    Action execution order is deterministic.
    """
    
    PARAM_DEFS = {
        "listen_events": ParamDef(list, [], "Event types to listen for"),
        "event_filter": ParamDef(dict, {}, "Event payload filter"),
        "actions": ParamDef(list, [], "Ordered action list"),
        "run_once": ParamDef(bool, False, "Only run once"),
        "cooldown": ParamDef(float, 0.0, "Time between runs"),
        "enabled": ParamDef(bool, True, "Whether active"),
        "require_flags": ParamDef(list, [], "Flags that must be true to trigger"),
        "forbid_flags": ParamDef(list, [], "Flags that must be false to trigger"),
    }
    
    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__
        self._enabled: bool = True
        self._pending_actions: List[Dict[str, Any]] = []
        self._pending_index: int = 0
        self._delay_remaining: float = 0.0
        self._run_count: int = 0
        self._last_triggered: float = 0.0
        self._cooldown_remaining: float = 0.0
        self._triggered_event: Optional[Dict[str, Any]] = None
        
        super().__init__(entity, window, **config)
        
        # Config
        listen = self.config.get("listen_events", [])
        if isinstance(listen, str):
            listen = [listen]
        self.listen_events: Set[str] = set(str(e) for e in listen if e)
        
        self.event_filter: Dict[str, Any] = dict(self.config.get("event_filter", {}))
        self.actions: List[Dict[str, Any]] = list(self.config.get("actions", []))
        self.run_once: bool = bool(self.config.get("run_once", False))
        self.cooldown: float = max(0.0, float(self.config.get("cooldown", 0.0)))
        self._enabled = bool(self.config.get("enabled", True))
        self.require_flags: List[str] = self._normalize_flag_list(self.config.get("require_flags"))
        self.forbid_flags: List[str] = self._normalize_flag_list(self.config.get("forbid_flags"))
    
    @property
    def enabled(self) -> bool:
        """Whether the runner is active."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)
    
    @property
    def is_running(self) -> bool:
        """Whether actions are currently being executed."""
        return bool(self._pending_actions)
    
    @property
    def run_count(self) -> int:
        """Number of times actions have been triggered."""
        return self._run_count
    
    def _matches_filter(self, payload: Dict[str, Any]) -> bool:
        """Check if event payload matches the filter."""
        if not self.event_filter:
            return True
        
        for key, expected in self.event_filter.items():
            actual = payload.get(key)
            if actual != expected:
                return False
        return True
    
    def _emit_event(self, event_type: str, **kwargs) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")
        
        payload = {
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            **kwargs,
        }

        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="ActionListRunner",
        )
    
    def _can_trigger(self) -> bool:
        """Check if action list can be triggered."""
        if not self._enabled:
            return False
        if self.is_running:
            return False  # Already executing
        if self.run_once and self._run_count > 0:
            return False
        if self._cooldown_remaining > 0:
            return False
        if not self._requirements_met():
            return False
        return True

    def _requirements_met(self) -> bool:
        if not self.require_flags and not self.forbid_flags:
            return True
        getter = self._resolve_flag_getter()
        if getter is None:
            return False
        for flag in self.require_flags:
            if not bool(getter(flag, False)):
                return False
        for flag in self.forbid_flags:
            if bool(getter(flag, False)):
                return False
        return True

    def _resolve_flag_getter(self):
        getter = getattr(self.window, "get_flag", None)
        if callable(getter):
            return getter
        game_state_ctrl = getattr(self.window, "game_state_controller", None)
        if game_state_ctrl is None:
            return None
        getter = getattr(game_state_ctrl, "get_flag", None)
        if callable(getter):
            return getter
        state = getattr(game_state_ctrl, "state", None)
        if state is None:
            return None
        return lambda name, default=False: state_flags.get_flag(state, name, default)

    @staticmethod
    def _normalize_flag_list(payload: Any) -> List[str]:
        values: List[str] = []
        if isinstance(payload, (list, tuple)):
            source = payload
        elif isinstance(payload, str):
            source = [part.strip() for part in payload.replace(";", ",").split(",")]
        else:
            source = []
        for entry in source:
            name = str(entry or "").strip()
            if name:
                values.append(name)
        return values
    
    def handle_event(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """Handle an incoming event.
        
        Args:
            event_type: Type of the event.
            payload: Event payload dict.
            
        Returns:
            True if action list was triggered.
        """
        if event_type not in self.listen_events:
            return False
        if not self._matches_filter(payload):
            return False
        if not self._can_trigger():
            return False
        
        # Start action execution
        self._pending_actions = list(self.actions)
        self._pending_index = 0
        self._delay_remaining = 0.0
        self._run_count += 1
        self._cooldown_remaining = self.cooldown
        self._triggered_event = dict(payload)
        
        # Emit start event
        self._emit_event(
            "action_list_started",
            run_count=self._run_count,
            action_count=len(self._pending_actions),
        )
        
        return True
    
    def _execute_action(self, action: Dict[str, Any]) -> bool:
        """Execute a single action.
        
        Args:
            action: Action configuration dict.
            
        Returns:
            True if action needs to wait (delay), False to continue.
        """
        action_type = str(action.get("type", "")).strip()
        
        if action_type == "emit_event":
            return self._action_emit_event(action)
        elif action_type == "set_flag":
            return self._action_set_flag(action, True)
        elif action_type == "clear_flag":
            return self._action_set_flag(action, False)
        elif action_type == "add_tag":
            return self._action_modify_tag(action, add=True)
        elif action_type == "remove_tag":
            return self._action_modify_tag(action, add=False)
        elif action_type == "start_timer":
            return self._action_timer(action, start=True)
        elif action_type == "stop_timer":
            return self._action_timer(action, start=False)
        elif action_type == "start_dialogue":
            return self._action_start_dialogue(action)
        elif action_type == "delay":
            return self._action_delay(action)
        
        # Unknown action type - skip
        return False
    
    def _action_emit_event(self, action: Dict[str, Any]) -> bool:
        """Execute emit_event action."""
        event_type = str(action.get("event_type", "")).strip()
        if not event_type:
            return False
        
        # Get payload, merging with triggered event if requested
        payload = dict(action.get("payload", {}))
        if action.get("include_trigger_payload"):
            trigger_payload = self._triggered_event or {}
            merged = dict(trigger_payload)
            merged.update(payload)
            payload = merged
        
        self._emit_event(event_type, **payload)
        return False
    
    def _action_set_flag(self, action: Dict[str, Any], value: bool) -> bool:
        """Execute set_flag or clear_flag action."""
        flag_name = str(action.get("flag", "")).strip()
        if not flag_name:
            return False
        
        # Get game state from window
        game_state_ctrl = getattr(self.window, "game_state_controller", None)
        if game_state_ctrl is None:
            return False
        
        state = getattr(game_state_ctrl, "state", None)
        if state is None:
            return False
        
        state_flags.set_flag(state, flag_name, value)
        return False
    
    def _action_modify_tag(self, action: Dict[str, Any], add: bool) -> bool:
        """Execute add_tag or remove_tag action."""
        tag = str(action.get("tag", "")).strip()
        if not tag:
            return False
        
        # Get target entity
        target = self._resolve_target(action)
        if target is None:
            return False
        
        # Get or create tags list
        tags = getattr(target, "mesh_tags", None)
        if tags is None:
            if add:
                setattr(target, "mesh_tags", [tag])
            return False
        
        if not isinstance(tags, list):
            tags = list(tags)
            setattr(target, "mesh_tags", tags)
        
        if add:
            if tag not in tags:
                tags.append(tag)
        else:
            if tag in tags:
                tags.remove(tag)
        
        return False
    
    def _action_timer(self, action: Dict[str, Any], start: bool) -> bool:
        """Execute start_timer or stop_timer action."""
        # Get target entity
        target = self._resolve_target(action)
        if target is None:
            return False
        
        # Find timer behaviour
        timer_id = str(action.get("timer_id", "")).strip()
        behaviours = getattr(target, "behaviours", None) or []
        
        for behaviour in behaviours:
            if type(behaviour).__name__ != "TimerBehaviour":
                continue
            
            # Match by timer_id if specified
            if timer_id:
                behaviour_timer_id = getattr(behaviour, "timer_id", "")
                if behaviour_timer_id != timer_id:
                    continue
            
            if start:
                if hasattr(behaviour, "start"):
                    behaviour.start()
            else:
                if hasattr(behaviour, "stop"):
                    behaviour.stop()
            
            # Only affect first matching timer unless "all" is set
            if not action.get("all"):
                break
        
        return False
    
    def _action_start_dialogue(self, action: Dict[str, Any]) -> bool:
        """Execute start_dialogue action."""
        # Get target entity
        target = self._resolve_target(action)
        if target is None:
            return False
        
        # Find dialogue runner behaviour
        dialogue_id = str(action.get("dialogue_id", "")).strip()
        behaviours = getattr(target, "behaviours", None) or []
        
        for behaviour in behaviours:
            if type(behaviour).__name__ != "DialogueRunnerBehaviour":
                continue
            
            # Match by dialogue_id if specified
            if dialogue_id:
                behaviour_dialogue_id = getattr(behaviour, "dialogue_id", "")
                if behaviour_dialogue_id != dialogue_id:
                    continue
            
            if hasattr(behaviour, "start"):
                node_id = action.get("node_id")
                behaviour.start(node_id)
            
            # Only start first matching dialogue
            break
        
        return False
    
    def _action_delay(self, action: Dict[str, Any]) -> bool:
        """Execute delay action (pause before next action)."""
        duration = float(action.get("duration", 0.0))
        if duration > 0:
            self._delay_remaining = duration
            return True  # Needs to wait
        return False
    
    def _resolve_target(self, action: Dict[str, Any]):
        """Resolve target entity from action config.
        
        Target can be:
        - "self" (default): This entity
        - entity_id: Specific entity by mesh_id
        - entity_name: Entity by mesh_name
        """
        target_spec = action.get("target", "self")
        
        if target_spec == "self" or not target_spec:
            return self.entity
        
        # Search for entity by ID or name
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return None
        
        sprites = getattr(scene_controller, "all_sprites", None)
        if sprites is None:
            sprites = getattr(scene_controller, "entities", None)
        if sprites is None:
            return None
        
        for sprite in sprites:
            if getattr(sprite, "mesh_id", None) == target_spec:
                return sprite
            if getattr(sprite, "mesh_name", None) == target_spec:
                return sprite
        
        return None
    
    def update(self, dt: float) -> None:
        """Update action execution and cooldowns."""
        # Update cooldown
        if self._cooldown_remaining > 0:
            self._cooldown_remaining = max(0.0, self._cooldown_remaining - dt)
        
        # Process pending actions
        if not self._pending_actions:
            return
        
        # Handle delay
        if self._delay_remaining > 0:
            self._delay_remaining -= dt
            if self._delay_remaining > 0:
                return  # Still waiting
        
        # Execute actions until delay or completion
        while self._pending_index < len(self._pending_actions):
            action = self._pending_actions[self._pending_index]
            self._pending_index += 1
            
            needs_wait = self._execute_action(action)
            if needs_wait:
                return  # Wait for delay
        
        # All actions completed
        self._emit_event(
            "action_list_completed",
            run_count=self._run_count,
            action_count=len(self._pending_actions),
        )
        self._pending_actions = []
        self._pending_index = 0
        self._triggered_event = None
    
    # SaveableBehaviour protocol
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "enabled": self._enabled,
            "pending_actions": list(self._pending_actions),
            "pending_index": self._pending_index,
            "delay_remaining": round(self._delay_remaining, 6),
            "run_count": self._run_count,
            "cooldown_remaining": round(self._cooldown_remaining, 6),
            "triggered_event": self._triggered_event,
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._enabled = bool(state.get("enabled", True))
        self._pending_actions = list(state.get("pending_actions", []))
        self._pending_index = int(state.get("pending_index", 0))
        self._delay_remaining = float(state.get("delay_remaining", 0.0))
        self._run_count = int(state.get("run_count", 0))
        self._cooldown_remaining = float(state.get("cooldown_remaining", 0.0))
        self._triggered_event = state.get("triggered_event")
    
    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state summary for editor inspection."""
        return {
            "enabled": self._enabled,
            "is_running": self.is_running,
            "run_count": self._run_count,
            "action_count": len(self.actions),
            "pending_index": self._pending_index if self.is_running else 0,
            "delay_remaining": round(self._delay_remaining, 2),
            "cooldown_remaining": round(self._cooldown_remaining, 2),
            "listening_to": list(self.listen_events),
            "require_flags": list(self.require_flags),
            "forbid_flags": list(self.forbid_flags),
        }


# =============================================================================
# Validation
# =============================================================================

def _validate_flag_list(
    field_name: str,
    value: Any,
    *,
    entity_id: str,
    behaviour_name: str,
) -> tuple[list[str], list[EventConfigError]]:
    errors: list[EventConfigError] = []
    if value is None:
        return ([], errors)
    if not isinstance(value, list):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=field_name,
            message=f"{field_name} must be a list of strings",
            hint=f"Use \"{field_name}\": [\"flag_name\", \"flag_group.flag\"]",
        ))
        return ([], errors)
    normalized: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for idx, entry in enumerate(value):
        if not isinstance(entry, str) or not entry.strip():
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{field_name}[{idx}]",
                message=f"{field_name}[{idx}] must be a non-empty string",
                hint="Provide a lowercase flag id like \"demo.objective_started\"",
            ))
            continue
        name = entry.strip()
        if not FLAG_ID_PATTERN.match(name):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{field_name}[{idx}]",
                message=f"{field_name}[{idx}] must match pattern {FLAG_ID_PATTERN_TEXT}",
                hint="Use lowercase letters, numbers, underscores, and dots (e.g. demo.objective_started)",
            ))
            continue
        if name in seen:
            if name not in duplicates:
                duplicates.append(name)
            continue
        seen.add(name)
        normalized.append(name)
    if duplicates:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=field_name,
            message=f"{field_name} contains duplicate entries: {duplicates}",
            hint=f"Deduplicate to: {normalized}",
        ))
    return (normalized, errors)

def validate_action(
    action: Dict[str, Any],
    index: int,
    *,
    entity_id: str = "",
    behaviour_name: str = "ActionListRunner",
) -> List[EventConfigError]:
    """Validate a single action config.
    
    Args:
        action: Action configuration dict.
        index: Index of action in list (for error path).
        entity_id: Entity ID for error reporting.
        behaviour_name: Behaviour name for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    path_prefix = f"actions[{index}]"
    
    if not isinstance(action, dict):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=path_prefix,
            message=f"action must be a dict, got {type(action).__name__}",
        ))
        return errors
    
    action_type = action.get("type")
    if not action_type:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=f"{path_prefix}.type",
            message="action type is required",
        ))
        return errors
    
    action_type = str(action_type).strip()
    if action_type not in VALID_ACTION_TYPES:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path=f"{path_prefix}.type",
            message=f"unknown action type: {action_type!r}. Valid types: {sorted(VALID_ACTION_TYPES)}",
        ))
        return errors
    
    # Type-specific validation
    if action_type == "emit_event":
        event_type = action.get("event_type")
        if not event_type:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.event_type",
                message="emit_event requires event_type",
            ))
        else:
            errors.extend(validate_event_type(
                event_type,
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.event_type",
            ))
    
    elif action_type in ("set_flag", "clear_flag"):
        flag = action.get("flag")
        if not flag or not str(flag).strip():
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.flag",
                message=f"{action_type} requires flag name",
            ))
    
    elif action_type in ("add_tag", "remove_tag"):
        tag = action.get("tag")
        if not tag or not str(tag).strip():
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.tag",
                message=f"{action_type} requires tag name",
            ))
    
    elif action_type == "delay":
        duration = action.get("duration")
        if duration is None:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.duration",
                message="delay requires duration",
            ))
        else:
            try:
                dur = float(duration)
                if dur < 0:
                    errors.append(EventConfigError(
                        entity_id=entity_id,
                        behaviour_name=behaviour_name,
                        config_path=f"{path_prefix}.duration",
                        message="delay duration must be non-negative",
                    ))
            except (TypeError, ValueError):
                errors.append(EventConfigError(
                    entity_id=entity_id,
                    behaviour_name=behaviour_name,
                    config_path=f"{path_prefix}.duration",
                    message=f"delay duration must be a number, got {type(duration).__name__}",
                ))
    
    return errors


def validate_action_list_runner_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate ActionListRunner configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "ActionListRunner"
    
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
    
    # Validate actions
    actions = config.get("actions", [])
    if not isinstance(actions, list):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="actions",
            message=f"actions must be a list, got {type(actions).__name__}",
        ))
    elif not actions:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="actions",
            message="actions must not be empty",
        ))
    else:
        for i, action in enumerate(actions):
            errors.extend(validate_action(
                action,
                index=i,
                entity_id=entity_id,
                behaviour_name=behaviour_name,
            ))
    
    # Validate cooldown
    cooldown = config.get("cooldown", 0.0)
    try:
        cooldown = float(cooldown)
        if cooldown < 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="cooldown",
                message="cooldown must be non-negative",
            ))
    except (TypeError, ValueError):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="cooldown",
                message=f"cooldown must be a number, got {type(cooldown).__name__}",
            ))

    # Validate require_flags / forbid_flags
    for field_name in ("require_flags", "forbid_flags"):
        _normalized, flag_errors = _validate_flag_list(
            field_name,
            config.get(field_name),
            entity_id=entity_id,
            behaviour_name=behaviour_name,
        )
        errors.extend(flag_errors)
    
    return errors
