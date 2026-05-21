from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import engine.optional_arcade as optional_arcade

from engine.ui_overlays.widgets import Rect, TextInput


class EditorItemEditorController:
    """Edit-mode controller for the Item Editor dock tab."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self.edit_mode_active = False
        self.edit_buffer: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._focused_field: str | None = None
        self._original_item: dict[str, Any] | None = None
        self._original_item_id: str | None = None
        self._id_input = TextInput(text="", placeholder="item_id", focused=False, font_size=12, height=18.0)
        self._button_rects: dict[str, Rect] = {}

    def enter_edit_mode(self, item: dict[str, Any]) -> None:
        self.edit_mode_active = True
        self._original_item = dict(item)
        self._original_item_id = str(item.get("id", "") or "")
        self.edit_buffer = dict(item)
        self.last_error = None
        self._focused_field = "id"
        self._id_input.text = str(self.edit_buffer.get("id", "") or "")
        self._id_input.focused = True

    def cancel_edit_mode(self) -> None:
        self.edit_mode_active = False
        self.edit_buffer = None
        self.last_error = None
        self._focused_field = None
        self._original_item = None
        self._original_item_id = None
        self._id_input.focused = False

    def commit_save(self, all_items: list[dict[str, Any]], target_path: str | Path) -> bool:
        if not self.edit_mode_active or self.edit_buffer is None:
            return False
        from engine.editor.item_editor_model import save_items, validate_item

        self._sync_id_input_to_buffer()
        candidate = dict(self.edit_buffer)
        original_id = str(self._original_item_id or candidate.get("id", "") or "")
        next_items = [dict(item) for item in all_items]
        replaced = False
        for index, item in enumerate(next_items):
            if str(item.get("id", "") or "") == original_id:
                next_items[index] = candidate
                replaced = True
                break
        if not replaced:
            next_items.append(candidate)

        errors = validate_item(candidate, next_items)
        if errors:
            self._set_save_error("; ".join(errors))
            return False
        try:
            save_items(next_items, target_path)
        except Exception as exc:  # noqa: BLE001  # REASON: save errors must stay visible in the form
            self._set_save_error(str(exc))
            return False

        self.cancel_edit_mode()
        self._emit_feedback_info("Item saved")
        return True

    def is_edit_mode_active(self) -> bool:
        return bool(self.edit_mode_active)

    def is_dirty(self) -> bool:
        if not self.edit_mode_active or self.edit_buffer is None or self._original_item is None:
            return False
        self._sync_id_input_to_buffer()
        return dict(self.edit_buffer) != dict(self._original_item)

    def focused_field(self) -> str | None:
        return self._focused_field

    def last_error_message(self) -> str | None:
        return self.last_error

    def id_input(self) -> TextInput:
        return self._id_input

    def set_button_rects(self, rects: dict[str, Rect]) -> None:
        self._button_rects = dict(rects)

    def handle_item_editor_text_input(self, text: str) -> bool:
        if not self.edit_mode_active or self._focused_field != "id":
            return False
        changed = self._id_input.on_text_input(text)
        if changed:
            self._sync_id_input_to_buffer()
        return bool(changed)

    def handle_item_editor_key(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.edit_mode_active:
            return False
        if key == optional_arcade.arcade.key.ESCAPE:
            self.cancel_edit_mode()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            changed = self._id_input.on_key_backspace()
            if changed:
                self._sync_id_input_to_buffer()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            if self._id_input.on_key_enter():
                self._id_input.focused = False
                self._focused_field = None
                self._sync_id_input_to_buffer()
            return True
        if key == optional_arcade.arcade.key.TAB:
            return True
        return True

    def handle_item_editor_mouse_click(self, x: float, y: float) -> bool:
        overlay = self._get_overlay()
        action = self._hit_button(float(x), float(y))
        if action == "edit":
            item = self._overlay_selected_item_dict(overlay)
            if item is None:
                return True
            self.edit_mode_active = True
            self.enter_edit_mode(item)
            return True
        if action == "cancel":
            self.cancel_edit_mode()
            return True
        if action == "save":
            all_items = self._overlay_all_item_dicts(overlay)
            target = self._items_target_path()
            ok = self.commit_save(all_items, target)
            if ok:
                reload_model = getattr(overlay, "reload_model", None)
                if callable(reload_model):
                    reload_model()
            return True

        if self.edit_mode_active:
            changed = self._id_input.on_mouse_press(float(x), float(y))
            self._focused_field = "id" if self._id_input.focused else None
            return bool(changed)
        return False

    def _sync_id_input_to_buffer(self) -> None:
        if self.edit_buffer is not None:
            self.edit_buffer["id"] = str(self._id_input.text or "").strip()

    def _hit_button(self, x: float, y: float) -> str | None:
        for action, rect in self._button_rects.items():
            if rect.contains(float(x), float(y)):
                return action
        return None

    def _get_overlay(self) -> Any | None:
        return getattr(getattr(self._editor, "window", None), "item_editor_overlay", None)

    def _items_target_path(self) -> Path:
        root_getter = getattr(self._editor, "_get_repo_root", None)
        root = Path(root_getter()) if callable(root_getter) else Path.cwd()
        return root / "assets" / "data" / "items.json"

    def _overlay_selected_item_dict(self, overlay: Any | None) -> dict[str, Any] | None:
        getter = getattr(overlay, "selected_item_dict", None) if overlay is not None else None
        if callable(getter):
            item = getter()
            return dict(item) if isinstance(item, dict) else None
        return None

    def _overlay_all_item_dicts(self, overlay: Any | None) -> list[dict[str, Any]]:
        getter = getattr(overlay, "all_item_dicts", None) if overlay is not None else None
        if callable(getter):
            return [dict(item) for item in getter()]
        return []

    def _set_save_error(self, message: str) -> None:
        self.last_error = str(message or "Unable to save item")
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "error", None) if feedback is not None else None
        if callable(reporter):
            reporter(self.last_error)

    def _emit_feedback_info(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
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
