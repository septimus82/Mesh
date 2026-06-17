from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController

_FOCUS_CYCLE = ("id", "name", "description", "icon", "max_stack")
_TAG_ACTION_KIND = "tag"
_EFFECT_ACTION_KIND = "effect"


class EditorItemEditorController(EditorDatabaseFormController):
    """Edit-mode controller for the Item Editor dock tab."""

    FORM_NAME = "Item"
    OVERLAY_ATTR = "item_editor_overlay"
    SAVE_SUCCESS_MESSAGE = "Item saved"
    SAVE_ERROR_FALLBACK = "Unable to save item"
    ID_FIELD = "id"
    FOCUS_CYCLE = _FOCUS_CYCLE
    TEXT_INPUT_SPECS = (
        ("id", "item_id"),
        ("name", "Item name"),
        ("description", "Description"),
        ("icon", "assets/..."),
        ("max_stack", "1"),
    )

    def handle_item_editor_text_input(self, text: str) -> bool:
        return self.handle_text_input(text)

    def handle_item_editor_key(self, key: int, modifiers: int) -> bool:
        return self.handle_key(key, modifiers)

    def handle_item_editor_mouse_click(self, x: float, y: float) -> bool:
        if not self.is_edit_mode_active():
            overlay = self._get_overlay()
            row_index_at = getattr(overlay, "row_index_at", None) if overlay is not None else None
            idx = row_index_at(float(x), float(y)) if callable(row_index_at) else None
            if idx is not None:
                overlay.set_selected_index(int(idx))
                return True
        else:
            overlay = self._get_overlay()
            action_at = getattr(overlay, "complex_entry_action_at", None) if overlay is not None else None
            action = action_at(float(x), float(y)) if callable(action_at) else None
            parsed_action = _complex_entry_action_parts(action)
            if parsed_action is not None:
                kind, ref, verb = parsed_action
                if kind == _TAG_ACTION_KIND and verb == "delete" and isinstance(ref, int):
                    return self._delete_tag(ref)
                if kind == _EFFECT_ACTION_KIND and verb == "delete" and isinstance(ref, str):
                    return self._delete_effect(ref)
        return self.handle_mouse_click(float(x), float(y))

    def _record_for_edit(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._normalized_buffer(dict(record))

    def _record_for_compare(self, record: dict[str, Any]) -> dict[str, Any]:
        return dict(record)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        if field == "id":
            record[field] = str(value or "").strip()
        elif field == "icon":
            icon = str(value or "").strip()
            record[field] = icon or None
        elif field == "max_stack":
            record[field] = str(value or "").strip()
        else:
            record[field] = str(value or "")

    def _get_field_value(self, record: dict[str, Any], field: str) -> Any:
        if field == "max_stack":
            return record.get(field, 1)
        return record.get(field)

    def _target_path(self) -> Path:
        from engine.editor.item_editor_model import DEFAULT_ITEMS_FILE_PATH  # noqa: PLC0415

        root_getter = getattr(self._editor, "_get_repo_root", None)
        root = Path(root_getter()) if callable(root_getter) else Path.cwd()
        return root / DEFAULT_ITEMS_FILE_PATH

    def _items_target_path(self) -> Path:
        return self._target_path()

    def _validate_records(
        self,
        candidate: dict[str, Any],
        next_records: list[dict[str, Any]],
        target_path: str | Path,  # noqa: ARG002
    ) -> list[str]:
        from engine.editor.item_editor_model import validate_item  # noqa: PLC0415

        return validate_item(candidate, next_records)

    def _save_records(self, records: list[dict[str, Any]], target_path: str | Path) -> None:
        from engine.editor.item_editor_model import save_items  # noqa: PLC0415

        save_items(records, target_path)

    def _overlay_selected_record(self, overlay: Any | None) -> dict[str, Any] | None:
        getter = getattr(overlay, "selected_item_dict", None) if overlay is not None else None
        if callable(getter):
            item = getter()
            return item_definition_to_dict(item) if item is not None else None
        return None

    def _overlay_all_records(self, overlay: Any | None) -> list[dict[str, Any]]:
        getter = getattr(overlay, "all_item_dicts", None) if overlay is not None else None
        if callable(getter):
            return [item_definition_to_dict(item) for item in getter()]
        return []

    def _handle_special_widget_click(self, clicked_field: str | None) -> bool:
        if clicked_field != "stackable":
            return False
        self._focused_field = None
        self._focus_field(None)
        return True

    def _delete_tag(self, index: int) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        tags = self.edit_buffer.get("tags")
        if not isinstance(tags, list) or not 0 <= int(index) < len(tags):
            return False
        self.sync_widgets_to_buffer()
        tags.pop(int(index))
        return True

    def _delete_effect(self, key: str) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        effects = self.edit_buffer.get("effects")
        if not isinstance(effects, dict) or key not in effects:
            return False
        self.sync_widgets_to_buffer()
        del effects[key]
        return True

    def _normalized_buffer(self, item: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(item)
        normalized["id"] = str(normalized.get("id", "") or "").strip()
        normalized["name"] = str(normalized.get("name", "") or "")
        normalized["description"] = str(normalized.get("description", "") or "")
        icon = str(normalized.get("icon", "") or "").strip()
        normalized["icon"] = icon or None
        normalized["stackable"] = bool(normalized.get("stackable", False))
        normalized["max_stack"] = str(normalized.get("max_stack", 1) or "").strip()
        normalized["tags"] = list(normalized.get("tags", []) or [])
        normalized["effects"] = dict(normalized.get("effects", {}) or {})
        return normalized


def item_definition_to_dict(item: Any) -> dict[str, Any]:
    """Convert an ItemDefinition-like object into the editable JSON shape."""
    if hasattr(item, "__dataclass_fields__"):
        return dict(asdict(item))
    if isinstance(item, dict):
        return dict(item)
    return {
        "id": str(getattr(item, "id", "") or ""),
        "name": str(getattr(item, "name", "") or ""),
        "description": str(getattr(item, "description", "") or ""),
        "icon": getattr(item, "icon", None),
        "stackable": bool(getattr(item, "stackable", False)),
        "max_stack": int(getattr(item, "max_stack", 1) or 1),
        "tags": list(getattr(item, "tags", []) or []),
        "effects": dict(getattr(item, "effects", {}) or {}),
    }


def _complex_entry_action_parts(action: object) -> tuple[str, int | str, str] | None:
    text = str(action or "")
    pieces = text.split(".")
    if len(pieces) < 3:
        return None
    kind = pieces[0]
    verb = pieces[-1]
    ref_text = ".".join(pieces[1:-1])
    if not ref_text or not verb:
        return None
    if kind == _TAG_ACTION_KIND:
        if not ref_text.isdigit():
            return None
        return kind, int(ref_text), verb
    if kind == _EFFECT_ACTION_KIND:
        return kind, ref_text, verb
    return None
