"""Read-only item editor model helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.inventory import ItemDatabase, ItemDefinition

DEFAULT_ITEMS_FILE_PATH = Path("assets") / "data" / "items.json"

ITEM_FIELD_ORDER = (
    "id",
    "name",
    "description",
    "icon",
    "stackable",
    "max_stack",
    "tags",
    "effects",
)

ITEM_SCALAR_FIELD_ORDER: tuple[str, ...] = ("id", "name", "description", "icon", "stackable", "max_stack")


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

    def set_selected_index(self, index: int) -> bool:
        return bool(self.select_index(int(index)))

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


def tag_rows(item: object) -> list[tuple[str, str]]:
    tags = _complex_field(item, "tags")
    if not isinstance(tags, list):
        return []
    return [(f"Tag {index}", tag) for index, tag in enumerate(tags) if isinstance(tag, str)]


def effect_rows(item: object) -> list[tuple[str, str]]:
    effects = _complex_field(item, "effects")
    if not isinstance(effects, dict):
        return []
    return [(key, str(effects[key])) for key in sorted(effects)]


def _complex_field(item: object, field_name: str) -> object:
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def validate_item(item: dict[str, Any], all_items: list[dict[str, Any]]) -> list[str]:
    """Return validation errors for one editable item payload."""
    errors: list[str] = []
    item_id = str(item.get("id", "") or "").strip()
    if not item_id:
        errors.append("id is required")
    elif _id_count(item_id, all_items) > 1:
        errors.append(f"id '{item_id}' is already used")

    try:
        if int(item.get("max_stack", 1)) < 1:
            errors.append("max_stack must be a positive integer")
    except (TypeError, ValueError):
        errors.append("max_stack must be a positive integer")
    return errors


def save_items(items: list[dict[str, Any]], target_path: str | Path) -> None:
    """Persist normalized item dictionaries and invalidate runtime item cache."""
    normalized = [_normalize_item_dict(item) for item in items]
    errors: list[str] = []
    for item in normalized:
        errors.extend(validate_item(item, normalized))
    if errors:
        raise ValueError("; ".join(errors))

    from engine import persistence_io
    from engine.inventory import clear_item_database_cache

    persistence_io.write_json_atomic(
        Path(target_path),
        {"items": normalized},
        indent=2,
        sort_keys=False,
        trailing_newline=True,
    )
    clear_item_database_cache()


def _id_count(item_id: str, items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if str(item.get("id", "") or "").strip() == item_id)


def _normalize_item_dict(item: dict[str, Any]) -> dict[str, Any]:
    stackable = bool(item.get("stackable", False))
    try:
        max_stack = int(item.get("max_stack", 99 if stackable else 1))
    except (TypeError, ValueError):
        max_stack = item.get("max_stack", 1)
    tags_raw = item.get("tags", [])
    effects_raw = item.get("effects", {})
    normalized = {
        "id": str(item.get("id", "") or "").strip(),
        "name": str(item.get("name") or item.get("id") or ""),
        "description": str(item.get("description") or ""),
        "icon": str(item.get("icon")) if item.get("icon") else None,
        "stackable": stackable,
        "max_stack": max_stack,
        "tags": [str(tag) for tag in tags_raw if str(tag).strip()] if isinstance(tags_raw, list) else [],
        "effects": dict(effects_raw) if isinstance(effects_raw, dict) else {},
    }
    return {key: normalized[key] for key in ITEM_FIELD_ORDER}
