"""Inventory holder behaviour for Mesh Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..inventory import get_or_create_inventory, load_item_database
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@dataclass(slots=True)
class HeldItem:
    item_id: str
    amount: int


@register_behaviour(
    "InventoryHolder",
    description="Stores configured inventory items and can transfer them into the shared inventory bucket.",
    config_fields=[
        {
            "name": "items",
            "description": "List of item ids or {id, amount} objects tied to assets/data/items.json.",
            "type": "array",
            "default": [],
        },
        {
            "name": "consume_on_transfer",
            "description": "Remove held items after transfer_to_inventory runs.",
            "type": "bool",
            "default": True,
        },
    ],
)
class InventoryHolder(Behaviour):
    """Keeps a lightweight item list for other behaviours (PickupCollectible, quests, etc.)."""

    PARAM_DEFS = {
        "items": ParamDef(list, default=[], description="List of item ids or entry objects."),
        "consume_on_transfer": ParamDef(bool, default=True, description="Remove held items after transfer."),
    }

    def __init__(self, entity, window, **config):  # type: ignore[override]
        super().__init__(entity, window, **config)
        self.consume_on_transfer = bool(self.config.get("consume_on_transfer", True))
        raw_items = self.config.get("items")
        self._items: list[HeldItem] = self._normalize_items(raw_items)
        self._validate_items()

    # ------------------------------------------------------------------
    # Public helpers consumed by other systems
    # ------------------------------------------------------------------
    def has_items(self) -> bool:
        return any(entry.amount > 0 for entry in self._items)

    def list_items(self) -> list[tuple[str, int]]:
        return [(entry.item_id, entry.amount) for entry in self._items if entry.amount > 0]

    def transfer_to_inventory(self, *, consume: bool | None = None) -> list[tuple[str, int]]:
        if not self._items:
            return []

        consume_flag = self.consume_on_transfer if consume is None else bool(consume)
        inventory = get_or_create_inventory(self.window.game_state.values)
        granted: list[tuple[str, int]] = []
        remaining: list[HeldItem] = []

        for entry in self._items:
            requested = max(0, int(entry.amount))
            if requested <= 0:
                if consume_flag:
                    continue
                remaining.append(entry)
                continue

            before = inventory.get_count(entry.item_id)
            inventory.add_item(entry.item_id, requested)
            after = inventory.get_count(entry.item_id)
            delta = max(0, after - before)
            if delta > 0:
                granted.append((entry.item_id, delta))
            leftover = max(0, requested - delta)
            if consume_flag and leftover > 0:
                remaining.append(HeldItem(entry.item_id, leftover))
            elif not consume_flag:
                remaining.append(entry)

        if consume_flag:
            self._items = remaining
        return granted

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _normalize_items(self, raw: Any) -> list[HeldItem]:
        entries: list[HeldItem] = []
        for entry in self._iterate_entries(raw):
            item_id, amount = self._extract_entry(entry)
            if not item_id or amount <= 0:
                continue
            entries.append(HeldItem(item_id=item_id, amount=amount))
        return entries

    def _iterate_entries(self, raw: Any) -> Iterable[Any]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            if any(key in raw for key in ("id", "item", "item_id")):
                return [raw]
            expanded: list[dict[str, Any]] = []
            for item_id, amount in raw.items():
                expanded.append({"id": item_id, "amount": amount})
            return expanded
        if isinstance(raw, (list, tuple)):
            return list(raw)
        if isinstance(raw, str):
            return [raw]
        return []

    def _extract_entry(self, entry: Any) -> tuple[str, int]:
        if isinstance(entry, str):
            return entry.strip(), 1
        if isinstance(entry, (list, tuple)) and entry:
            item_id = str(entry[0]).strip()
            amount = 1
            if len(entry) > 1:
                amount = self._coerce_amount(entry[1])
            return item_id, max(0, amount)
        if isinstance(entry, dict):
            raw_id = entry.get("id") or entry.get("item") or entry.get("item_id")
            item_id = str(raw_id or "").strip()
            amount = self._coerce_amount(entry.get("amount", entry.get("count", 1)))
            return item_id, max(0, amount)
        return "", 0

    def _coerce_amount(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive fallback
            return 0

    def _validate_items(self) -> None:
        if not self._items:
            return
        try:
            db = load_item_database()
        except Exception as exc:  # pragma: no cover - load failure already logged elsewhere
            print(f"[Mesh][InventoryHolder] WARNING: Unable to load item database: {exc}")
            return
        valid: list[HeldItem] = []
        for entry in self._items:
            if db.get(entry.item_id) is None:
                print(f"[Mesh][InventoryHolder] WARNING: Unknown item id '{entry.item_id}'")
                continue
            valid.append(entry)
        self._items = valid
