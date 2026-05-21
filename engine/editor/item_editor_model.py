"""Read-only item editor model helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.inventory import ItemDatabase, ItemDefinition


@dataclass
class ItemEditorModel:
    """Read-only view model for authoring items from assets/data/items.json."""

    items: list[ItemDefinition]
    selected_index: int = 0

    @classmethod
    def load(cls, root: str | Path | None = None) -> "ItemEditorModel":
        database = ItemDatabase.load(root)
        return cls(items=list(database.items.values()))

    @property
    def item_count(self) -> int:
        return len(self.items)

    @property
    def selected_item(self) -> ItemDefinition | None:
        if not self.items:
            return None
        index = self._clamp_index(self.selected_index)
        self.selected_index = index
        return self.items[index]

    def select_index(self, index: int) -> bool:
        if not self.items:
            changed = self.selected_index != 0
            self.selected_index = 0
            return changed
        next_index = self._clamp_index(index)
        changed = next_index != self.selected_index
        self.selected_index = next_index
        return changed

    def move_selection(self, delta: int) -> bool:
        return self.select_index(self.selected_index + int(delta))

    def list_rows(self) -> list[str]:
        return [f"{item.name} ({item.id})" for item in self.items]

    def selected_detail_rows(self) -> list[tuple[str, str]]:
        item = self.selected_item
        if item is None:
            return []
        rows: list[tuple[str, str]] = [
            ("ID", item.id),
            ("Name", item.name),
        ]
        if item.description:
            rows.append(("Description", item.description))
        if item.icon:
            rows.append(("Icon", item.icon))
        if item.stackable:
            rows.append(("Stackable", "true"))
        if item.max_stack != 1:
            rows.append(("Max stack", str(item.max_stack)))
        if item.tags:
            rows.append(("Tags", ", ".join(item.tags)))
        if item.effects:
            rows.append(("Effects", _format_effects(item.effects)))
        return rows

    def _clamp_index(self, index: int) -> int:
        if not self.items:
            return 0
        return max(0, min(int(index), len(self.items) - 1))


def _format_effects(effects: dict[str, Any]) -> str:
    return ", ".join(f"{key}={effects[key]}" for key in sorted(effects))
