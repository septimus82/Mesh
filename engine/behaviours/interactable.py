"""Interactable behaviour - key press when focused/near emits on_interact.

Allows entities to be interacted with when the player is nearby and presses
the interact key. Emits deterministic events for interaction handling.

Events emitted:
- on_interact: When an entity interacts with this object

Save/restore:
- Tracks interaction count and cooldown state
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from ..event_emit import emit_gameplay_event
from ..events import MeshEvent
from ..gameplay_event_bus import EventConfigError, validate_event_type
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "Interactable",
    description="Emits on_interact when a nearby entity presses the interact key.",
    config_fields=[
        {
            "name": "interact_radius",
            "description": "Maximum distance for interaction",
            "type": "float",
            "default": 48.0,
        },
        {
            "name": "interact_key",
            "description": "Key binding name for interaction (e.g., 'interact', 'use')",
            "type": "string",
            "default": "interact",
        },
        {
            "name": "interact_event",
            "description": "Event type to emit on interaction",
            "type": "string",
            "default": "on_interact",
        },
        {
            "name": "interact_label",
            "description": "UI label shown when in range",
            "type": "string",
            "default": "Interact",
        },
        {
            "name": "target_tags",
            "description": "Tags of entities that can interact (empty = 'player')",
            "type": "array",
            "default": ["player"],
        },
        {
            "name": "cooldown",
            "description": "Minimum time between interactions (seconds)",
            "type": "float",
            "default": 0.5,
        },
        {
            "name": "one_shot",
            "description": "If true, can only be interacted with once",
            "type": "bool",
            "default": False,
        },
        {
            "name": "enabled",
            "description": "Whether interaction is active",
            "type": "bool",
            "default": True,
        },
        {
            "name": "require_line_of_sight",
            "description": "Require unobstructed path to interactor",
            "type": "bool",
            "default": False,
        },
    ],
)
class InteractableBehaviour(Behaviour):
    """Key press when focused/near emits on_interact.
    
    Implements SaveableBehaviour for deterministic save/restore.
    """

    PARAM_DEFS = {
        "interact_radius": ParamDef(float, 48.0, "Maximum distance for interaction"),
        "interact_key": ParamDef(str, "interact", "Key binding name"),
        "interact_event": ParamDef(str, "on_interact", "Event type to emit"),
        "interact_label": ParamDef(str, "Interact", "UI label when in range"),
        "target_tags": ParamDef(list, ["player"], "Tags that can interact"),
        "cooldown": ParamDef(float, 0.5, "Time between interactions"),
        "one_shot": ParamDef(bool, False, "Can only interact once"),
        "enabled": ParamDef(bool, True, "Whether interaction is active"),
        "require_line_of_sight": ParamDef(bool, False, "Require unobstructed path"),
    }

    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__ (which calls setattr for params)
        self._enabled: bool = True
        self._interaction_count: int = 0
        self._cooldown_remaining: float = 0.0
        self._in_range_entity: str | None = None
        self._consumed: bool = False

        super().__init__(entity, window, **config)

        # Config
        self.interact_radius = float(self.config.get("interact_radius", 48.0))
        self.interact_key = str(self.config.get("interact_key", "interact"))
        self.interact_event = str(self.config.get("interact_event", "on_interact"))
        self.interact_label = str(self.config.get("interact_label", "Interact"))
        self.cooldown = float(self.config.get("cooldown", 0.5))
        self.one_shot = bool(self.config.get("one_shot", False))
        self._enabled = bool(self.config.get("enabled", True))
        self.require_line_of_sight = bool(self.config.get("require_line_of_sight", False))

        # Parse target tags
        raw_tags = self.config.get("target_tags") or ["player"]
        self.target_tags: List[str] = [str(t) for t in raw_tags if t]

    @property
    def enabled(self) -> bool:
        """Whether interaction is active."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def can_interact(self) -> bool:
        """Whether interaction is currently possible."""
        if not self._enabled:
            return False
        if self.one_shot and self._consumed:
            return False
        if self._cooldown_remaining > 0:
            return False
        return True

    def _find_interactor_in_range(self):
        """Find the closest valid interactor in range."""
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return None

        sprites = getattr(scene_controller, "all_sprites", None)
        if sprites is None:
            sprites = getattr(scene_controller, "entities", None)
        if sprites is None:
            return None

        my_x = float(self.entity.center_x)
        my_y = float(self.entity.center_y)

        closest = None
        closest_dist = float("inf")

        for sprite in sprites:
            if sprite is self.entity:
                continue

            # Check tags
            entity_tags = set(getattr(sprite, "mesh_tags", []) or [])
            if self.target_tags and not (entity_tags & set(self.target_tags)):
                continue

            # Check distance
            dx = float(sprite.center_x) - my_x
            dy = float(sprite.center_y) - my_y
            dist = math.hypot(dx, dy)

            if dist <= self.interact_radius and dist < closest_dist:
                closest = sprite
                closest_dist = dist

        return closest

    def _get_entity_id(self, sprite) -> str:
        """Get deterministic ID for an entity."""
        return str(
            getattr(sprite, "mesh_id", None)
            or getattr(sprite, "mesh_name", None)
            or id(sprite)
        )

    def _emit_event(self, interactor) -> None:
        """Emit the interaction event."""
        interactor_id = self._get_entity_id(interactor)
        my_id = getattr(self.entity, "mesh_id", "")
        payload = {
            "target": my_id,
            "target_name": getattr(self.entity, "mesh_name", ""),
            "interactor": interactor_id,
            "interactor_name": getattr(interactor, "mesh_name", ""),
            "position": (float(self.entity.center_x), float(self.entity.center_y)),
            "interaction_count": self._interaction_count,
        }

        emit_gameplay_event(
            self.window,
            self.interact_event,
            payload,
            source_entity_id=my_id,
            source_behaviour="Interactable",
        )

    def can_interact_with(self, actor: Any) -> bool:
        """Return whether the provided actor may currently use this interaction."""
        if not self.can_interact:
            return False
        if actor is None:
            return False
        entity_tags = set(getattr(actor, "mesh_tags", []) or [])
        mesh_tag = getattr(actor, "mesh_tag", None)
        if mesh_tag:
            entity_tags.add(str(mesh_tag))
        if self.target_tags and not (entity_tags & set(self.target_tags)):
            return False
        try:
            dx = float(getattr(actor, "center_x")) - float(getattr(self.entity, "center_x"))
            dy = float(getattr(actor, "center_y")) - float(getattr(self.entity, "center_y"))
        except (TypeError, ValueError, AttributeError):
            return False
        return math.hypot(dx, dy) <= float(self.interact_radius)

    def get_interact_label(self, _actor: Any = None) -> str | None:
        return self.interact_label

    def on_interact(self, window: Any, actor: Any) -> None:  # noqa: ARG002
        self.try_interact(actor)

    def try_interact(self, interactor: Any | None = None) -> bool:
        """Attempt to interact with this object.
        
        Returns:
            True if interaction occurred.
        """
        if interactor is None:
            interactor = self._find_interactor_in_range()
        if interactor is None:
            return False
        if not self.can_interact_with(interactor):
            return False

        # Perform interaction
        self._interaction_count += 1
        self._cooldown_remaining = self.cooldown

        if self.one_shot:
            self._consumed = True

        self._emit_event(interactor)
        return True

    def update(self, dt: float) -> None:
        """Update cooldown and check for in-range entities."""
        # Update cooldown
        if self._cooldown_remaining > 0:
            self._cooldown_remaining = max(0.0, self._cooldown_remaining - dt)

        # Update in-range tracking for UI hints
        if self._enabled and not (self.one_shot and self._consumed):
            interactor = self._find_interactor_in_range()
            self._in_range_entity = self._get_entity_id(interactor) if interactor else None
        else:
            self._in_range_entity = None

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset()

    def on_event(self, event: MeshEvent) -> None:  # noqa: ARG002
        """Interactable no longer listens to input events directly."""
        return

    # SaveableBehaviour protocol
    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable state dict."""
        return {
            "enabled": self._enabled,
            "interaction_count": self._interaction_count,
            "cooldown_remaining": round(self._cooldown_remaining, 4),
            "consumed": self._consumed,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        """Apply previously saved state."""
        self._enabled = bool(state.get("enabled", True))
        self._interaction_count = int(state.get("interaction_count", 0))
        self._cooldown_remaining = float(state.get("cooldown_remaining", 0.0))
        self._consumed = bool(state.get("consumed", False))

    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state summary for editor inspection."""
        return {
            "enabled": self._enabled,
            "can_interact": self.can_interact,
            "interaction_count": self._interaction_count,
            "cooldown_remaining": round(self._cooldown_remaining, 2),
            "consumed": self._consumed,
            "in_range": self._in_range_entity is not None,
            "in_range_entity": self._in_range_entity,
        }


def validate_interactable_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate Interactable configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "Interactable"

    # Validate interact_radius
    radius = config.get("interact_radius", 48.0)
    try:
        radius = float(radius)
        if radius <= 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="interact_radius",
                message="interact_radius must be positive",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="interact_radius",
            message=f"interact_radius must be a number, got {type(radius).__name__}",
        ))

    # Validate cooldown
    cooldown = config.get("cooldown", 0.5)
    try:
        cooldown = float(cooldown)
        if cooldown < 0:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path="cooldown",
                message="cooldown cannot be negative",
            ))
    except (TypeError, ValueError):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="cooldown",
            message=f"cooldown must be a number, got {type(cooldown).__name__}",
        ))

    # Validate interact_event
    interact_event = config.get("interact_event", "on_interact")
    if interact_event:
        errors.extend(validate_event_type(
            interact_event,
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="interact_event",
        ))

    return errors
