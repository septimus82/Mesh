from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController, _get_path, _set_path

_FOCUS_CYCLE = ("id", "name", "description", "icon", "max_stack")
TAG_ADD_ACTION = "tag.add"
EFFECT_ADD_ACTION = "effect.add"
_TAG_ACTION_KIND = "tag"
_EFFECT_ACTION_KIND = "effect"
_EFFECT_FIELD_PREFIX = "effects."
_EFFECT_KEY_FIELD_PREFIX = "effect_key."
# Curated soft-warning vocabulary for runtime-known effects; custom keys remain allowed.
_KNOWN_EFFECT_KEYS = frozenset(
    {
        "attack",
        "attack_bonus",
        "damage",
        "damage_bonus",
        "damage_pct",
        "defense",
        "defense_bonus",
        "gold_bonus_pct",
        "heal",
        "hp_bonus",
        "max_hp",
        "max_hp_bonus",
        "quest_flag",
        "speed",
        "speed_bonus",
        "tier",
        "xp_bonus_pct",
    }
)


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

    def __init__(self, editor: Any) -> None:
        super().__init__(editor)
        self._pending_effect_key_focus: str | None = None

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
            if action == TAG_ADD_ACTION:
                return self._add_tag()
            if action == EFFECT_ADD_ACTION:
                return self._add_effect()
            parsed_action = _complex_entry_action_parts(action)
            if parsed_action is not None:
                kind, ref, verb = parsed_action
                if kind == _TAG_ACTION_KIND and verb == "delete" and isinstance(ref, int):
                    return self._delete_tag(ref)
                if kind == _EFFECT_ACTION_KIND and verb == "delete" and isinstance(ref, str):
                    return self._delete_effect(ref)
        return self.handle_mouse_click(float(x), float(y))

    def enter_edit_mode(self, record: dict[str, Any]) -> None:
        self._rebuild_text_inputs(record)
        super().enter_edit_mode(record)

    def cancel_edit_mode(self) -> None:
        super().cancel_edit_mode()
        self._rebuild_text_inputs(None)

    def _record_for_edit(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._normalized_buffer(dict(record))

    def _record_for_compare(self, record: dict[str, Any]) -> dict[str, Any]:
        return dict(record)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        if field.startswith(_EFFECT_KEY_FIELD_PREFIX):
            self._set_effect_key_field_value(record, field, value)
            return
        if field.startswith(_EFFECT_FIELD_PREFIX):
            self._set_effect_field_value(record, field, value)
            return
        if "." in field:
            _set_path(record, field, str(value or ""))
            return
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
        if field.startswith(_EFFECT_KEY_FIELD_PREFIX):
            return field.removeprefix(_EFFECT_KEY_FIELD_PREFIX)
        if field.startswith(_EFFECT_FIELD_PREFIX):
            effects = record.get("effects")
            key = field.removeprefix(_EFFECT_FIELD_PREFIX)
            return effects.get(key) if isinstance(effects, dict) else None
        if "." in field:
            return _get_path(record, field)
        if field == "max_stack":
            return record.get(field, 1)
        return record.get(field)

    def _set_effect_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        effects = record.get("effects")
        key = field.removeprefix(_EFFECT_FIELD_PREFIX)
        if not isinstance(effects, dict) or key not in effects:
            return
        original = effects[key]
        text = str(value or "")
        try:
            effects[key] = _coerce_effect_value(original, text)
        except ValueError:
            self._set_save_error(f"Invalid numeric value for {field}: {text}")

    def _set_effect_key_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        effects = record.get("effects")
        old_key = field.removeprefix(_EFFECT_KEY_FIELD_PREFIX)
        if not isinstance(effects, dict) or old_key not in effects:
            return
        new_key = str(value or "").strip()
        if new_key == old_key:
            return
        if not new_key:
            self._set_save_error(f"Effect key for {old_key} cannot be empty")
            return
        if new_key in effects:
            self._set_save_error(f"Effect key '{new_key}' already exists")
            return
        renamed = {
            (new_key if key == old_key else key): effect_value
            for key, effect_value in effects.items()
        }
        effects.clear()
        effects.update(renamed)
        self._pending_effect_key_focus = f"{_EFFECT_KEY_FIELD_PREFIX}{new_key}"
        if new_key not in _KNOWN_EFFECT_KEYS:
            self._emit_feedback_warning(f"Unknown item effect key '{new_key}'")

    def _rebuild_text_inputs(self, record: dict[str, Any] | None) -> None:
        from engine.ui_overlays.widgets import TextInput  # noqa: PLC0415

        specs = list(self.TEXT_INPUT_SPECS)
        tags = record.get("tags") if isinstance(record, dict) else None
        if isinstance(tags, list):
            specs.extend((f"tags.{index}", f"Tag {index}") for index, _tag in enumerate(tags))
        effects = record.get("effects") if isinstance(record, dict) else None
        if isinstance(effects, dict):
            for key in sorted(effects):
                specs.append((f"{_EFFECT_KEY_FIELD_PREFIX}{key}", "Effect key"))
                specs.append((f"effects.{key}", f"Effect {key}"))
        self._text_inputs = {}
        for field, placeholder in specs:
            value = self._get_field_value(record or {}, field)
            self._text_inputs[field] = TextInput(
                text="" if value is None else str(value),
                placeholder=placeholder,
                focused=False,
                font_size=12,
                height=18.0,
            )

    def sync_widgets_to_buffer(self) -> None:
        self._pending_effect_key_focus = None
        super().sync_widgets_to_buffer()
        if self.edit_buffer is None or self._pending_effect_key_focus is None:
            return
        focus_field = self._pending_effect_key_focus
        self._pending_effect_key_focus = None
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(focus_field)

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

    def _add_tag(self) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        self.sync_widgets_to_buffer()
        tags = self.edit_buffer.get("tags")
        if not isinstance(tags, list):
            tags = []
            self.edit_buffer["tags"] = tags
        new_index = len(tags)
        tags.append("new_tag")
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"tags.{new_index}")
        return True

    def _add_effect(self) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        self.sync_widgets_to_buffer()
        effects = self.edit_buffer.get("effects")
        if not isinstance(effects, dict):
            effects = {}
            self.edit_buffer["effects"] = effects
        key = _next_effect_key(effects)
        effects[key] = 0
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"effects.{key}")
        return True

    def _delete_tag(self, index: int) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        tags = self.edit_buffer.get("tags")
        if not isinstance(tags, list) or not 0 <= int(index) < len(tags):
            return False
        self.sync_widgets_to_buffer()
        tags.pop(int(index))
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        return True

    def _delete_effect(self, key: str) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        effects = self.edit_buffer.get("effects")
        if not isinstance(effects, dict) or key not in effects:
            return False
        self.sync_widgets_to_buffer()
        del effects[key]
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
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

    def _emit_feedback_warning(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "warning", None) if feedback is not None else None
        if not callable(reporter):
            reporter = getattr(feedback, "info", None) if feedback is not None else None
        if callable(reporter):
            reporter(message)


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


def _coerce_effect_value(original: Any, text: str) -> int | float | str:
    if isinstance(original, bool):
        return text
    if isinstance(original, int):
        return int(text)
    if isinstance(original, float):
        return float(text)
    return text


def _next_effect_key(effects: dict[str, Any]) -> str:
    existing_keys = set(effects)
    candidate_index = 1
    while True:
        suffix = "" if candidate_index == 1 else f"_{candidate_index}"
        candidate = f"new_effect{suffix}"
        if candidate not in existing_keys:
            return candidate
        candidate_index += 1


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
