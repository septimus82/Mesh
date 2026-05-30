"""Base behaviour definitions for Mesh Engine.

Behaviours are reusable components that attach to entities to provide game logic.
They follow an Entity-Component pattern where each behaviour encapsulates a specific
capability (movement, AI, animation, interaction, etc.).

Key Concepts:
    - Behaviours are attached to entities via the ``behaviours`` list in scene JSON
    - Each behaviour receives the entity sprite and game window reference
    - Parameters are declared via ``PARAM_DEFS`` class attribute for type coercion
    - Lifecycle hooks: ``pre_update`` -> ``update`` -> ``late_update``
    - Event handling via ``on_event`` for responding to gameplay events

Example Usage (in scene JSON)::

    {
        "name": "Enemy",
        "x": 100, "y": 200,
        "behaviours": [
            {"type": "Patrol", "speed": 50, "points": [[0, 0], [100, 0]]},
            {"type": "Health", "max_hp": 100}
        ]
    }

Creating a Custom Behaviour::

    class MyBehaviour(Behaviour):
        PARAM_DEFS = {
            "speed": ParamDef(float, 100.0, "Movement speed in pixels/sec"),
            "enabled": ParamDef(bool, True, "Whether behaviour is active"),
        }

        def update(self, dt: float) -> None:
            if self.enabled:
                self.entity.center_x += self.speed * dt

Save/Load Contract:
    Behaviours with runtime state that should persist across saves must implement
    the SaveableBehaviour protocol from :mod:`engine.behaviours.saveable`:
    
    - ``saveable_state() -> dict``: Return JSON-serializable state dict
    - ``restore_state(state: dict) -> None``: Apply previously saved state
    
    Optional versioning support:
    
    - ``STATE_VERSION: int``: Schema version for migration support
    - ``migrate_state(old_state, from_version) -> dict``: Migrate old formats
    
    Example::
    
        class Health(Behaviour):
            STATE_VERSION = 1
            
            def saveable_state(self) -> dict[str, Any]:
                return {"current_hp": self.current_hp}
                
            def restore_state(self, state: dict[str, Any]) -> None:
                self.current_hp = state.get("current_hp", self.max_hp)

See Also:
    - :mod:`engine.behaviours.registry` for behaviour registration
    - :mod:`engine.behaviours.saveable` for save/load protocol
    - :doc:`docs/behaviours` for full behaviour documentation
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Mapping

if TYPE_CHECKING:  # pragma: no cover - import guard for typing only
    from arcade import Sprite

    from engine.game import GameWindow

    from ..events import MeshEvent


@dataclass(slots=True)
class ParamDef:
    """Describes a typed behaviour parameter with optional default and documentation.

    ParamDefs enable automatic type coercion from JSON config values to Python types,
    provide default values when parameters are omitted, and generate documentation.

    Attributes:
        type: Expected Python type or type name string. Supported values:
            - ``int``, ``float``, ``bool``, ``str`` (or string equivalents)
            - ``list``/``tuple``/``"array"`` for sequences
            - ``dict``/``"object"`` for mappings
        default: Value used when parameter is not provided in config.
            Mutable defaults (list, dict) are deep-copied per instance.
        description: Human-readable description for documentation/tooling.

    Example::

        PARAM_DEFS = {
            "speed": ParamDef(float, 100.0, "Movement speed in pixels/second"),
            "tags": ParamDef(list, [], "Entity tags for filtering"),
        }
    """

    type: type | str
    default: Any = None
    description: str = ""


class Behaviour:
    """Base class for all entity behaviours in Mesh Engine.

    Behaviours encapsulate reusable game logic that can be attached to entities.
    Subclasses override lifecycle methods to implement specific functionality.

    Lifecycle Methods (called each frame in order):
        1. ``pre_update(dt)``: Setup/input processing before movement
        2. ``update(dt)``: Main logic (movement, AI decisions, etc.)
        3. ``late_update(dt)``: Post-movement cleanup (collision response, etc.)

    Class Attributes:
        PARAM_DEFS: Dictionary mapping parameter names to :class:`ParamDef` instances.
            Defines the configuration schema for this behaviour type.

    Instance Attributes:
        entity: The Arcade Sprite this behaviour is attached to.
        window: Reference to the main :class:`GameWindow` for accessing game systems.
        config: Merged configuration dict with coerced parameter values.

    Example::

        class FollowPlayer(Behaviour):
            PARAM_DEFS = {
                "speed": ParamDef(float, 50.0, "Follow speed"),
                "min_distance": ParamDef(float, 32.0, "Stop distance"),
            }

            def update(self, dt: float) -> None:
                player = self.window.scene_controller.player
                if player:
                    dx = player.center_x - self.entity.center_x
                    dy = player.center_y - self.entity.center_y
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist > self.min_distance:
                        self.entity.center_x += (dx/dist) * self.speed * dt
                        self.entity.center_y += (dy/dist) * self.speed * dt
    """

    PARAM_DEFS: Dict[str, ParamDef] = {}

    def __init__(self, entity: "Sprite", window: "GameWindow", **config: Any) -> None:
        """Initialize a behaviour instance.

        Args:
            entity: The sprite this behaviour controls.
            window: The game window providing access to all engine systems.
            **config: Configuration parameters that override PARAM_DEFS defaults.
        """
        self.entity = entity
        self.window = window
        self._explicit_params: set[str] = set()
        self.config: dict[str, Any] = self._merge_param_config(config)

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------
    @classmethod
    def param_defs(cls) -> dict[str, ParamDef]:
        """Return normalized parameter definitions declared on the class."""

        raw_defs = getattr(cls, "PARAM_DEFS", {}) or {}
        normalized: dict[str, ParamDef] = {}
        for name, definition in raw_defs.items():
            param = cls._coerce_param_def(definition)
            normalized[str(name)] = param
        return normalized

    @staticmethod
    def _coerce_param_def(definition: Any) -> ParamDef:
        if isinstance(definition, ParamDef):
            return definition
        if isinstance(definition, Mapping):
            return ParamDef(
                type=definition.get("type", str),
                default=definition.get("default"),
                description=definition.get("description", ""),
            )
        if isinstance(definition, tuple):
            length = len(definition)
            param_type = definition[0] if length >= 1 else str
            default = definition[1] if length >= 2 else None
            description = definition[2] if length >= 3 else ""
            return ParamDef(type=param_type, default=default, description=description)
        return ParamDef(type=str, default=definition)

    def _merge_param_config(self, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        """Merge PARAM_DEFS defaults with provided config overrides.

        For each parameter defined in PARAM_DEFS:
            1. Check if override value was provided
            2. Coerce value to expected type (or use default)
            3. Set as instance attribute for convenient access
            4. Track which params were explicitly provided

        Args:
            overrides: Config dict from scene JSON or programmatic creation.

        Returns:
            Merged config dict with all parameters resolved.
        """
        incoming = dict(overrides or {})
        merged: dict[str, Any] = {}
        for name, definition in self.param_defs().items():
            raw_value = incoming.pop(name, _PARAM_SENTINEL)
            value = self._coerce_param_value(raw_value, definition)
            if raw_value is not _PARAM_SENTINEL:
                self._explicit_params.add(name)
            merged[name] = value
            setattr(self, name, value)
        for key, value in incoming.items():
            merged[key] = value
        return merged

    def _coerce_param_value(self, raw_value: Any, definition: ParamDef) -> Any:
        if raw_value is _PARAM_SENTINEL:
            return self._clone_default(definition.default)
        expected = definition.type
        kind = self._resolve_param_type(expected)
        try:
            if kind == "float":
                return float(raw_value)
            if kind == "int":
                return int(raw_value)
            if kind == "bool":
                if isinstance(raw_value, str):
                    lowered = raw_value.strip().lower()
                    if lowered in {"1", "true", "yes", "on"}:
                        return True
                    if lowered in {"0", "false", "no", "off"}:
                        return False
                return bool(raw_value)
            if kind == "array":
                if isinstance(raw_value, list):
                    return list(raw_value)
                if isinstance(raw_value, tuple):
                    return list(raw_value)
                if isinstance(raw_value, str):
                    return [chunk.strip() for chunk in raw_value.split(",") if chunk.strip()]
                return self._clone_default(definition.default or [])
            if kind == "object":
                if isinstance(raw_value, dict):
                    return dict(raw_value)
                return self._clone_default(definition.default or {})
            if kind == "string":
                if raw_value is None:
                    return ""
                return str(raw_value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return self._clone_default(definition.default)
        return raw_value

    @staticmethod
    def _clone_default(value: Any) -> Any:
        if isinstance(value, (dict, list, set)):  # pragma: no cover - trivial
            return copy.deepcopy(value)
        return value

    @staticmethod
    def _resolve_param_type(expected: type | str | None) -> str:
        if expected in {int, "int"}:
            return "int"
        if expected in {float, "float"}:
            return "float"
        if expected in {bool, "bool"}:
            return "bool"
        if expected in {list, tuple, "array"}:
            return "array"
        if expected in {dict, "object"}:
            return "object"
        return "string"

    def pre_update(self, dt: float) -> None:  # pragma: no cover - default no-op
        """Called before physics/movement processing each frame.

        Use for input handling, state machine transitions, or any setup
        that should happen before the entity moves.

        Args:
            dt: Delta time in seconds since last frame.
        """
        return

    def update(self, dt: float) -> None:  # pragma: no cover - default no-op
        """Main update called each frame for core behaviour logic.

        This is where most behaviour logic should live: movement, AI decisions,
        timer updates, animation state changes, etc.

        Args:
            dt: Delta time in seconds since last frame.
        """
        return

    def late_update(self, dt: float) -> None:  # pragma: no cover - default no-op
        """Called after physics/collisions are resolved each frame.

        Use for post-movement adjustments, collision response cleanup,
        or any logic that depends on final entity positions.

        Args:
            dt: Delta time in seconds since last frame.
        """
        return

    def subscribed_event_types(self) -> "frozenset[str] | None":
        """Event types this behaviour may act on. None = wildcard (receives all).

        Override to return a frozenset of event type strings this behaviour
        cares about. The delivery loop skips calling ``on_event`` when the
        incoming event type is not in the declared set, saving a call.

        Return ``None`` (the default) to receive every event — identical to
        the behaviour before this mechanism existed.

        Return ``frozenset()`` to opt out of all event delivery entirely (useful
        for behaviours that never handle events).

        Example::

            def subscribed_event_types(self) -> frozenset[str] | None:
                return frozenset({self.event_type}) if self.event_type else frozenset()
        """
        return None

    def on_event(self, event: "MeshEvent") -> None:  # pragma: no cover - default no-op
        """Handle a gameplay event broadcast through the event bus.

        Events are delivered to all behaviours on all entities. Filter by
        event.type and event.payload to respond only to relevant events.

        Common event types:
            - ``damage_applied``: Entity took damage
            - ``collectible_picked``: Item collected
            - ``quest_stage_complete``: Quest progress
            - ``animation_event``: Animation frame event

        Args:
            event: The MeshEvent containing type and payload dict.

        Example::

            def on_event(self, event: MeshEvent) -> None:
                if event.type == "damage_applied":
                    if event.payload.get("target") == self.entity.name:
                        self.flash_red()
        """
        return


_PARAM_SENTINEL = object()
