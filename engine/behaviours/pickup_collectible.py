"""Interactable collectible behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from arcade import Sprite

from ..constants import EVENT_COLLECTED
from ..events import MeshEvent
from ..inventory import get_or_create_inventory, load_item_database
from .base import Behaviour, ParamDef
from .inventory_holder import InventoryHolder
from .registry import register_behaviour


@register_behaviour(
    "PickupCollectible",
    description="Allows a sprite to be collected via the interact action.",
    config_fields=[
        {
            "name": "collector_tag",
            "description": "Sprite tag required to collect",
            "type": "string",
            "default": "player",
        },
        {
            "name": "remove_on_collect",
            "description": "Remove sprite after pickup",
            "type": "bool",
            "default": True,
        },
        {
            "name": "once",
            "description": "Only allow a single pickup",
            "type": "bool",
            "default": True,
        },
        {
            "name": "item_id",
            "description": "Item id to grant when collected (uses assets/data/items.json)",
            "type": "string",
            "default": "",
        },
        {
            "name": "item_amount",
            "description": "Quantity granted for item_id",
            "type": "int",
            "default": 1,
        },
    ],
)
class PickupCollectible(Behaviour):
    """Allows the player to pick up an entity via the interact action."""

    PARAM_DEFS = {
        "collector_tag": ParamDef(str, default="player", description="Sprite tag required to collect"),
        "remove_on_collect": ParamDef(bool, default=True, description="Remove sprite after pickup"),
        "once": ParamDef(bool, default=True, description="Only allow a single pickup"),
        "item_id": ParamDef(str, default="", description="Item id granted when collected"),
        "item_amount": ParamDef(int, default=1, description="Quantity granted for item_id"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        merged: Dict[str, Any] = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            merged.update(config)
        super().__init__(entity, window, **merged)

        raw_tag = self.config.get("collector_tag", "player")
        self.allowed_tag = str(raw_tag).strip() if raw_tag not in (None, "") else None
        self.remove_on_collect = bool(self.config.get("remove_on_collect", True))
        self.once = bool(self.config.get("once", True))
        raw_item_id = self.config.get("item_id") or self.config.get("item")
        self.item_id = str(raw_item_id).strip() if raw_item_id not in (None, "") else None
        self.item_amount = self._coerce_amount(self.config.get("item_amount", 1))
        self._already_collected: bool = False

    def on_interact(self, window, actor: Sprite) -> None:
        if self.once and self._already_collected:
            return

        if self.allowed_tag:
            actor_tag = getattr(actor, "mesh_tag", None)
            if actor_tag != self.allowed_tag:
                return

        self._already_collected = True

        granted_items = self._grant_inventory_items(window)

        payload = {
            "collectible": getattr(self.entity, "mesh_name", "<unnamed>"),
            "collector": getattr(actor, "mesh_name", "<unnamed>"),
            "position": (float(self.entity.center_x), float(self.entity.center_y)),
            "tag": getattr(self.entity, "mesh_tag", None),
            "amount": 1,
        }

        if granted_items:
            payload["items"] = [
                {"id": item_id, "amount": amount}
                for (item_id, amount) in granted_items
            ]

        # Use the event bus directly
        window.event_bus.emit(EVENT_COLLECTED, **payload)

        # Also emit the legacy event for compatibility if needed
        window.emit_event(MeshEvent(type="collect", payload=payload))

        window.console_log(
            f"Collected {payload['collectible']} via interact",
        )

        if granted_items:
            self._log_inventory_gain(window, granted_items)

        if self.remove_on_collect:
            self.entity.remove_from_sprite_lists()
        else:
            self.entity.visible = False

    # ------------------------------------------------------------------
    # Inventory helpers
    # ------------------------------------------------------------------
    def _grant_inventory_items(self, window) -> list[tuple[str, int]]:
        granted: list[tuple[str, int]] = []
        if self.item_id and self.item_amount > 0:
            granted.extend(self._grant_item(window, self.item_id, self.item_amount))
        holder = self._find_inventory_holder()
        if holder is not None:
            granted.extend(holder.transfer_to_inventory())
        return granted

    def _grant_item(self, window, item_id: str, amount: int) -> list[tuple[str, int]]:
        inventory = get_or_create_inventory(window.game_state.values)
        before = inventory.get_count(item_id)
        inventory.add_item(item_id, amount)
        after = inventory.get_count(item_id)
        delta = max(0, after - before)
        if delta <= 0:
            return []
        return [(item_id, delta)]

    def _find_inventory_holder(self) -> Optional[InventoryHolder]:
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            if isinstance(behaviour, InventoryHolder):
                return behaviour
        return None

    def _log_inventory_gain(self, window, granted_items: list[tuple[str, int]]) -> None:
        summary: dict[str, int] = {}
        for item_id, amount in granted_items:
            if amount <= 0:
                continue
            summary[item_id] = summary.get(item_id, 0) + amount
        if not summary:
            return
        db = load_item_database()
        parts = []
        for item_id, amount in summary.items():
            definition = db.get(item_id)
            label = definition.name if definition else item_id
            parts.append(f"{label} x{amount}")
        if parts:
            window.console_log("Inventory + " + ", ".join(parts))

    def _coerce_amount(self, value: Any, *, default: int = 1) -> int:
        try:
            amount = int(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive fallback
            amount = default
        return max(0, amount)
