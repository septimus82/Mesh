"""Read-only prefab editor model helpers."""

from __future__ import annotations

from json import dumps as _format_structured_value
from pathlib import Path
from typing import Any

DEFAULT_PREFAB_FILE_PATH = Path("assets") / "prefabs.json"

PREFAB_SCALAR_FIELD_ORDER = (
    "id",
    "display_name",
    "entity.sprite",
    "entity.encounter_cost",
)

PREFAB_COMPLEX_FIELD_ORDER = (
    "tags",
    "require_flags",
    "forbid_flags",
    "entity.behaviours",
    "entity.behaviour_config",
    "entity.require_flags",
    "metadata",
)


class PrefabEditorModel:
    """Read-only view model for authoring prefabs from assets/prefabs.json."""

    def __init__(self, prefab_manager: Any | None = None) -> None:
        if prefab_manager is None:
            from engine.prefabs import get_prefab_manager

            prefab_manager = get_prefab_manager()
        self._prefab_manager = prefab_manager
        self._prefabs: list[dict[str, Any]] = []
        self._selected_index = 0

    @classmethod
    def load(cls, prefab_manager: Any | None = None) -> "PrefabEditorModel":
        model = cls(prefab_manager)
        model.reload()
        return model

    def reload(self) -> None:
        loader = getattr(self._prefab_manager, "load", None)
        if callable(loader):
            loader(force=True)
        raw = getattr(self._prefab_manager, "prefabs", {})
        if isinstance(raw, dict):
            prefabs = [dict(value) for value in raw.values() if isinstance(value, dict)]
        elif isinstance(raw, list):
            prefabs = [dict(value) for value in raw if isinstance(value, dict)]
        else:
            prefabs = []
        self._prefabs = prefabs
        self._selected_index = self._clamp_index(self._selected_index)

    def prefabs(self) -> list[dict[str, Any]]:
        return [dict(prefab) for prefab in self._prefabs]

    @property
    def prefab_count(self) -> int:
        return len(self._prefabs)

    def selected_index(self) -> int:
        self._selected_index = self._clamp_index(self._selected_index)
        return self._selected_index

    def set_selected_index(self, index: int) -> bool:
        next_index = self._clamp_index(index)
        changed = next_index != self._selected_index
        self._selected_index = next_index
        return changed

    def selected_prefab(self) -> dict[str, Any] | None:
        if not self._prefabs:
            self._selected_index = 0
            return None
        return dict(self._prefabs[self.selected_index()])

    def list_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for prefab in self._prefabs:
            prefab_id = _string_value(prefab.get("id"))
            label = _string_value(prefab.get("display_name")) or prefab_id
            rows.append((label, prefab_id))
        return rows

    def scalar_detail_rows(self) -> list[tuple[str, str, str]]:
        prefab = self.selected_prefab()
        if prefab is None:
            return []
        rows: list[tuple[str, str, str]] = []
        for field_path in PREFAB_SCALAR_FIELD_ORDER:
            value = _get_path(prefab, field_path)
            if value is None or value == "":
                continue
            rows.append((_label_for_field(field_path), _format_value(value), field_path))
        return rows

    def complex_detail_rows(self) -> list[tuple[str, str]]:
        prefab = self.selected_prefab()
        if prefab is None:
            return []
        rows: list[tuple[str, str]] = []
        for field_path in PREFAB_COMPLEX_FIELD_ORDER:
            value = _get_path(prefab, field_path)
            if _is_empty_complex_value(value):
                continue
            rows.append((_label_for_field(field_path), _format_value(value)))
        return rows

    def _clamp_index(self, index: int) -> int:
        if not self._prefabs:
            return 0
        return max(0, min(int(index), len(self._prefabs) - 1))


def validate_prefab_entries(entries: list[dict[str, Any]], target_path: str | Path) -> list[str]:
    """Return validation error messages for editable prefab payloads."""
    from engine.validators.schema_validation import validate_prefab_file

    errors = validate_prefab_file(Path(target_path), entries)
    return [error.message for error in errors]


def save_prefabs(entries: list[dict[str, Any]], target_path: str | Path) -> None:
    """Persist prefab dictionaries through the editor prefab write path."""
    errors = validate_prefab_entries(entries, target_path)
    if errors:
        raise ValueError("; ".join(errors))

    from engine.editor.editor_prefab_controller import write_prefabs

    write_prefabs(Path(target_path), entries)


def _get_path(payload: dict[str, Any], field_path: str) -> Any:
    current: Any = payload
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _label_for_field(field_path: str) -> str:
    return {
        "id": "ID",
        "display_name": "Display name",
        "entity.sprite": "Sprite",
        "entity.encounter_cost": "Encounter cost",
        "tags": "Tags",
        "require_flags": "Require flags",
        "forbid_flags": "Forbid flags",
        "entity.behaviours": "Behaviours",
        "entity.behaviour_config": "Behaviour config",
        "entity.require_flags": "Entity require flags",
        "metadata": "Metadata",
    }.get(field_path, field_path)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return ", ".join(str(item) for item in value)
    try:
        text = _format_structured_value(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        text = repr(value)
    return text if len(text) <= 96 else f"{text[:93]}..."


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _is_empty_complex_value(value: Any) -> bool:
    return value is None or value == [] or value == {}
