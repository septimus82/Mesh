"""Timer behaviour - emits after duration, optionally repeats.

Provides deterministic time-based event emission with pause/resume support.
All timing is based on delta time accumulation for deterministic replay.

Events emitted:
- Configurable event type when timer fires

Save/restore:
- Tracks elapsed time and pause state
- Deterministic on restore
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError, validate_event_type
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "Timer",
    description="Emits an event after a duration, optionally repeating.",
    config_fields=[
        {
            "name": "duration",
            "description": "Time in seconds before firing",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "repeat",
            "description": "If true, restarts after firing",
            "type": "bool",
            "default": False,
        },
        {
            "name": "repeat_count",
            "description": "Number of times to repeat (-1 = infinite)",
            "type": "int",
            "default": -1,
        },
        {
            "name": "timer_event",
            "description": "Event type to emit when timer fires",
            "type": "string",
            "default": "on_timer",
        },
        {
            "name": "auto_start",
            "description": "Start timer automatically on creation",
            "type": "bool",
            "default": True,
        },
        {
            "name": "timer_id",
            "description": "Optional identifier for this timer",
            "type": "string",
            "default": "",
        },
        {
            "name": "enabled",
            "description": "Whether the timer is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class TimerBehaviour(Behaviour):
    """Timer that emits after duration, optionally repeats.
    
    Implements SaveableBehaviour for deterministic save/restore.
    All timing is deterministic based on accumulated delta time.
    """
    
    PARAM_DEFS = {
        "duration": ParamDef(float, 1.0, "Time before firing"),
        "repeat": ParamDef(bool, False, "Restart after firing"),
        "repeat_count": ParamDef(int, -1, "Times to repeat (-1 = infinite)"),
        "timer_event": ParamDef(str, "on_timer", "Event type to emit"),
        "auto_start": ParamDef(bool, True, "Start automatically"),
        "timer_id": ParamDef(str, "", "Timer identifier"),
        "enabled": ParamDef(bool, True, "Whether active"),
    }
    
    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__ (which calls setattr for params)
        self._enabled: bool = True
        self._elapsed: float = 0.0
        self._running: bool = False
        self._fire_count: int = 0
        self._completed: bool = False
        self._paused: bool = False
        
        super().__init__(entity, window, **config)
        
        # Config (extract from merged config)
        self.duration = max(0.001, float(self.config.get("duration", 1.0)))
        self.repeat = bool(self.config.get("repeat", False))
        self.repeat_count = int(self.config.get("repeat_count", -1))
        self.timer_event = str(self.config.get("timer_event", "on_timer"))
        self.auto_start = bool(self.config.get("auto_start", True))
        self.timer_id = str(self.config.get("timer_id", "")).strip()
        self._enabled = bool(self.config.get("enabled", True))
        
        # Set initial running state after config is loaded
        self._running = self.auto_start and self._enabled
    
    @property
    def enabled(self) -> bool:
        """Whether the timer is active."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        was_enabled = self._enabled
        self._enabled = bool(value)
        if not was_enabled and self._enabled and self.auto_start:
            self._running = True
    
    @property
    def is_running(self) -> bool:
        """Whether the timer is currently counting."""
        return self._running and not self._paused
    
    @property
    def time_remaining(self) -> float:
        """Time remaining until next fire."""
        return max(0.0, self.duration - self._elapsed)
    
    @property
    def progress(self) -> float:
        """Progress toward next fire (0.0 to 1.0)."""
        if self.duration <= 0:
            return 1.0
        return min(1.0, self._elapsed / self.duration)
    
    def start(self) -> None:
        """Start or restart the timer."""
        self._elapsed = 0.0
        self._running = True
        self._paused = False
        self._completed = False
    
    def stop(self) -> None:
        """Stop the timer without resetting."""
        self._running = False
    
    def pause(self) -> None:
        """Pause the timer (can be resumed)."""
        self._paused = True
    
    def resume(self) -> None:
        """Resume a paused timer."""
        self._paused = False
    
    def reset(self) -> None:
        """Reset the timer to initial state."""
        self._elapsed = 0.0
        self._fire_count = 0
        self._completed = False
        self._running = self.auto_start and self._enabled
        self._paused = False
    
    def _should_repeat(self) -> bool:
        """Check if timer should repeat after firing."""
        if not self.repeat:
            return False
        if self.repeat_count < 0:
            return True  # Infinite
        return self._fire_count < self.repeat_count
    
    def _emit_event(self) -> None:
        """Emit the timer event."""
        my_id = getattr(self.entity, "mesh_id", "")
        payload = {
            "timer_id": self.timer_id or my_id,
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            "fire_count": self._fire_count,
            "duration": self.duration,
        }
        emit_gameplay_event(
            self.window,
            self.timer_event,
            payload,
            source_entity_id=my_id,
            source_behaviour="Timer",
        )
    
    def update(self, dt: float) -> None:
        """Update timer and fire if duration reached."""
        if not self._enabled or not self._running or self._paused or self._completed:
            return
        
        # Accumulate time deterministically
        self._elapsed += dt
        
        # Check for fire
        while self._elapsed >= self.duration:
            self._fire_count += 1
            self._emit_event()
            
            if self._should_repeat():
                # Subtract duration for deterministic repeat
                self._elapsed -= self.duration
            else:
                # Stop timer
                self._elapsed = self.duration
                self._running = False
                self._completed = True
                break
    
    # SaveableBehaviour protocol
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "enabled": self._enabled,
            "elapsed": round(self._elapsed, 6),
            "running": self._running,
            "paused": self._paused,
            "fire_count": self._fire_count,
            "completed": self._completed,
        }
    
    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._enabled = bool(state.get("enabled", True))
        self._elapsed = float(state.get("elapsed", 0.0))
        self._running = bool(state.get("running", False))
        self._paused = bool(state.get("paused", False))
        self._fire_count = int(state.get("fire_count", 0))
        self._completed = bool(state.get("completed", False))
    
    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state summary for editor inspection."""
        return {
            "enabled": self._enabled,
            "duration": self.duration,
            "elapsed": round(self._elapsed, 2),
            "time_remaining": round(self.time_remaining, 2),
            "progress": round(self.progress, 2),
            "running": self._running,
            "paused": self._paused,
            "fire_count": self._fire_count,
            "completed": self._completed,
            "repeat": self.repeat,
            "repeat_count": self.repeat_count,
        }


def validate_timer_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate Timer configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "Timer"
    
    # Validate duration
    duration = config.get("duration", 1.0)
    try:
        duration = float(duration)
        if duration <= 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="duration",
                message="duration must be positive",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="duration",
            message=f"duration must be a number, got {type(duration).__name__}",
        ))
    
    # Validate repeat_count
    repeat_count = config.get("repeat_count", -1)
    try:
        repeat_count = int(repeat_count)
        if repeat_count < -1:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="repeat_count",
                message="repeat_count must be >= -1",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="repeat_count",
            message=f"repeat_count must be an integer, got {type(repeat_count).__name__}",
        ))
    
    # Validate timer_event
    timer_event = config.get("timer_event", "on_timer")
    if timer_event:
        errors.extend(validate_event_type(
            timer_event,
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="timer_event",
        ))
    
    return errors
