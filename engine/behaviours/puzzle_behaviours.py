"""Puzzle interaction behaviours."""

from __future__ import annotations

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from arcade import Sprite

from ..event_emit import emit_gameplay_event
from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "SwitchInteract",
    description="Emits an event when interacted with.",
    config_fields=[
        {
            "name": "event_id",
            "description": "Event ID to emit",
            "type": "string",
            "default": "",
        },
        {
            "name": "one_shot",
            "description": "If true, can only be used once",
            "type": "bool",
            "default": False,
        },
        {
            "name": "active_sprite",
            "description": "Sprite path for active state",
            "type": "string",
            "default": "",
        },
    ],
)
class SwitchInteract(Behaviour):
    """Emits an event when interacted with."""

    PARAM_DEFS = {
        "event_id": ParamDef(str, default="", description="Event ID to emit"),
        "one_shot": ParamDef(bool, default=False, description="If true, can only be used once"),
        "active_sprite": ParamDef(str, default="", description="Sprite path for active state"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.event_id = config.get("event_id", "")
        self.one_shot = config.get("one_shot", False)
        self.active_sprite = config.get("active_sprite", "")
        self.activated = False

    def on_interact(self, interactor: Sprite) -> None:
        if self.activated and self.one_shot:
            return

        if not self.event_id:
            return

        self.activated = True
        emit_gameplay_event(
            getattr(self.window, "event_bus", None),
            MeshEvent(self.event_id, {"source": self.entity}),
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="SwitchInteract",
        )

        # Visual feedback
        if self.active_sprite:
            # In a real engine we'd swap the texture.
            # For now, let's just log or maybe change color if possible.
            # self.entity.texture = load_texture(self.active_sprite)
            pass

        print(f"[Puzzle] Switch {self.entity} activated, emitted '{self.event_id}'")


@register_behaviour(
    "DoorLock",
    description="Unlocks when a specific event is received.",
    config_fields=[
        {
            "name": "unlock_event",
            "description": "Event ID that unlocks this door",
            "type": "string",
            "default": "",
        },
        {
            "name": "starts_locked",
            "description": "If true, starts in locked state",
            "type": "bool",
            "default": True,
        },
        {
            "name": "open_sprite",
            "description": "Sprite path for open state",
            "type": "string",
            "default": "",
        },
    ],
)
class DoorLock(Behaviour):
    """Unlocks when a specific event is received."""

    PARAM_DEFS = {
        "unlock_event": ParamDef(str, default="", description="Event ID that unlocks this door"),
        "starts_locked": ParamDef(bool, default=True, description="If true, starts in locked state"),
        "open_sprite": ParamDef(str, default="", description="Sprite path for open state"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.unlock_event = config.get("unlock_event", "")
        self.locked = config.get("starts_locked", True)
        self.open_sprite = config.get("open_sprite", "")

        self._unsubscribe = None
        if self.unlock_event:
            self._unsubscribe = self.window.event_bus.subscribe(self.unlock_event, self._on_unlock_event)

        self._update_collision()

    def _on_unlock_event(self, event: MeshEvent) -> None:
        if not self.locked:
            return

        print(f"[Puzzle] Door {self.entity} unlocked by event '{event.type}'")
        self.locked = False
        self._update_collision()

        # Emit door_unlocked event for chaining.
        emit_gameplay_event(
            getattr(self.window, "event_bus", None),
            MeshEvent("door_unlocked", {"door_id": getattr(self.entity, "id", "unknown")}),
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="DoorLock",
        )

    def _update_collision(self) -> None:
        # If locked, it should be solid. If unlocked, pass-through.
        # This depends on how the physics engine handles tags or properties.
        # Assuming 'solid' tag or property.
        if self.locked:
            # Ensure it blocks
            pass
        else:
            # Disable collision
            # In arcade, we might remove from wall list or change properties
            if hasattr(self.entity, "properties"):
                self.entity.properties["solid"] = False
                self.entity.properties["walkable"] = True

    def destroy(self) -> None:
        """Unsubscribe from event bus on teardown."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None


@register_behaviour(
    "RewardChest",
    description="Spawns or enables a reward when unlocked.",
    config_fields=[
        {
            "name": "unlock_event",
            "description": "Event ID that reveals the reward",
            "type": "string",
            "default": "",
        },
        {
            "name": "item_id",
            "description": "Item ID to reward",
            "type": "string",
            "default": "",
        },
        {
            "name": "gold",
            "description": "Amount of gold to reward",
            "type": "int",
            "default": 0,
        },
    ],
)
class RewardChest(Behaviour):
    """Spawns or enables a reward when unlocked."""

    PARAM_DEFS = {
        "unlock_event": ParamDef(str, default="", description="Event ID that reveals the reward"),
        "item_id": ParamDef(str, default="", description="Item ID to reward"),
        "gold": ParamDef(int, default=0, description="Amount of gold to reward"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.unlock_event = config.get("unlock_event", "")
        self.item_id = config.get("item_id", "")
        self.gold = config.get("gold", 0)
        self.looted = False

        self._unsubscribe = None
        if self.unlock_event:
            self._unsubscribe = self.window.event_bus.subscribe(self.unlock_event, self._on_unlock_event)
            # Start hidden/disabled if waiting for event?
            # For now, let's assume it's a chest that unlocks, not spawns.
            # Or maybe it spawns. Let's assume it's visible but locked until event?
            # The prompt says "spawn or enable on door_unlocked".
            # Let's assume it's enabled (interactable) only after event.
            self.enabled = False
        else:
            self.enabled = True

    def _on_unlock_event(self, event: MeshEvent) -> None:
        self.enabled = True
        print(f"[Puzzle] RewardChest {self.entity} enabled by '{event.type}'")

    def destroy(self) -> None:
        """Unsubscribe from event bus on teardown."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def on_interact(self, interactor: Sprite) -> None:
        if not self.enabled or self.looted:
            return

        self.looted = True
        print(f"[Puzzle] RewardChest looted! Item: {self.item_id}, Gold: {self.gold}")

        # Grant rewards
        # Assuming interactor has inventory
        if hasattr(interactor, "inventory"):
            if self.item_id:
                interactor.inventory.add_item(self.item_id)
            if self.gold:
                interactor.inventory.add_gold(self.gold)

        emit_gameplay_event(
            self.window,
            "reward_collected",
            {
                "source": self.entity,
                "item_id": self.item_id,
                "gold": self.gold,
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="RewardChest",
        )
