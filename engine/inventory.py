"""Inventory and item database helpers for Mesh Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple, cast

_ITEM_DB_CACHE: "ItemDatabase | None" = None


def load_item_database(root: str | Path | None = None) -> "ItemDatabase":
    global _ITEM_DB_CACHE
    if _ITEM_DB_CACHE is not None:
        return _ITEM_DB_CACHE
    db = ItemDatabase.load(root)
    _ITEM_DB_CACHE = db
    return db


@dataclass(slots=True)
class ItemDefinition:
    id: str
    name: str
    description: str
    icon: str | None
    stackable: bool
    max_stack: int
    tags: list[str]
    effects: dict[str, Any]


class ItemDatabase:
    def __init__(self, items: Dict[str, ItemDefinition]) -> None:
        self.items = items

    @classmethod
    def load(cls, root: str | Path | None = None) -> "ItemDatabase":
        base = Path(root or Path.cwd())
        data_path = base / "assets" / "data" / "items.json"
        if not data_path.exists():
            raise FileNotFoundError(f"Item database not found at {data_path}")
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        entries = raw.get("items", []) if isinstance(raw, dict) else []
        items: Dict[str, ItemDefinition] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("id", "")).strip()
            if not item_id:
                continue
            if item_id in items:
                raise ValueError(f"Duplicate item id '{item_id}' in items.json")
            stackable = bool(entry.get("stackable", False))
            max_stack = int(entry.get("max_stack", 99 if stackable else 1))
            items[item_id] = ItemDefinition(
                id=item_id,
                name=str(entry.get("name") or item_id),
                description=str(entry.get("description") or ""),
                icon=str(entry.get("icon")) if entry.get("icon") else None,
                stackable=stackable,
                max_stack=max(1, max_stack),
                tags=[str(tag) for tag in entry.get("tags", []) if str(tag).strip()],
                effects=dict(entry.get("effects", {})) if isinstance(entry.get("effects"), dict) else {},
            )
        return cls(items)

    def get(self, item_id: str) -> ItemDefinition | None:
        return self.items.get(item_id)

    def suggest(self, target: str) -> str | None:
        from difflib import get_close_matches

        if not target:
            return None
        matches = get_close_matches(target.lower(), [key.lower() for key in self.items], n=1, cutoff=0.65)
        if matches:
            lookup = {key.lower(): key for key in self.items}
            return lookup[matches[0]]
        return None


@dataclass
class Inventory:
    state_bucket: Dict[str, Any]

    def __post_init__(self) -> None:
        items = self.state_bucket.setdefault("items", {})
        if not isinstance(items, dict):
            items = {}
            self.state_bucket["items"] = items
        self._state = items

    def add_item(self, item_id: str, count: int = 1) -> bool:
        if count <= 0:
            return False
        item = load_item_database().get(item_id)
        if item is None:
            return False
        bucket = int(self._state.get(item_id, 0))
        max_stack = item.max_stack if item.stackable else 1
        new_total = min(max_stack, bucket + count)
        self._state[item_id] = new_total
        return new_total > bucket

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        if count <= 0:
            return False
        current = int(self._state.get(item_id, 0))
        if current <= 0:
            return False
        remaining = max(0, current - count)
        if remaining <= 0:
            self._state.pop(item_id, None)
        else:
            self._state[item_id] = remaining
        return True

    def get_count(self, item_id: str) -> int:
        return int(self._state.get(item_id, 0))

    def has_item(self, item_id: str, count: int = 1) -> bool:
        return self.get_count(item_id) >= max(1, count)

    def list_items(self) -> Iterator[Tuple[str, int]]:
        for item_id, amount in sorted(self._state.items()):
            yield item_id, int(amount)

    def clear(self) -> None:
        self._state.clear()


def get_inventory_bucket(game_state_values: Dict[str, Any]) -> Dict[str, Any]:
    return cast(Dict[str, Any], game_state_values.setdefault("inventory", {}))


def get_or_create_inventory(game_state_values: Dict[str, Any]) -> Inventory:
    bucket = get_inventory_bucket(game_state_values)
    return Inventory(bucket)
