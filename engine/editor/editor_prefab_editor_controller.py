from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import engine.optional_arcade as optional_arcade

from engine.ui_overlays.widgets import Rect, TextInput

_FOCUS_CYCLE = ("id",)


class EditorPrefabEditorController:
    """Edit-mode controller for the Prefab Editor dock tab."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        self.edit_mode_active = False
        self.edit_buffer: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._focused_field: str | None = None
        self._original_prefab: dict[str, Any] | None = None
        self._original_prefab_id: str | None = None
        self._text_inputs: dict[str, TextInput] = {
            "id": TextInput(text="", placeholder="prefab_id", focused=False, font_size=12, height=18.0),
        }
        self._button_rects: dict[str, Rect] = {}

    def enter_edit_mode(self, prefab: dict[str, Any]) -> None:
        self.edit_mode_active = True
        self._original_prefab = copy.deepcopy(prefab)
        self._original_prefab_id = str(prefab.get("id", "") or "")
        self.edit_buffer = copy.deepcopy(prefab)
        self.last_error = None
        self._focused_field = "id"
        self._sync_widgets_from_buffer()
        self._focus_field("id")

    def cancel_edit_mode(self) -> None:
        self.edit_mode_active = False
        self.edit_buffer = None
        self.last_error = None
        self._focused_field = None
        self._original_prefab = None
        self._original_prefab_id = None
        for widget in self._text_inputs.values():
            widget.focused = False

    def commit_save(self, all_prefabs: list[dict[str, Any]], target_path: str | Path) -> bool:
        if not self.edit_mode_active or self.edit_buffer is None:
            return False
        from engine.editor.prefab_editor_model import save_prefabs, validate_prefab_entries

        self.sync_widgets_to_buffer()
        candidate = copy.deepcopy(self.edit_buffer)
        original_id = str(self._original_prefab_id or candidate.get("id", "") or "")
        next_prefabs = [copy.deepcopy(prefab) for prefab in all_prefabs]
        replaced = False
        for index, prefab in enumerate(next_prefabs):
            if str(prefab.get("id", "") or "") == original_id:
                next_prefabs[index] = candidate
                replaced = True
                break
        if not replaced:
            next_prefabs.append(candidate)

        errors = validate_prefab_entries(next_prefabs, target_path)
        if errors:
            self._set_save_error("; ".join(errors))
            return False
        try:
            save_prefabs(next_prefabs, target_path)
        except Exception as exc:  # noqa: BLE001  # REASON: save errors must stay visible in the form
            self._set_save_error(str(exc))
            return False

        self.cancel_edit_mode()
        self._emit_feedback_info("Prefab saved")
        return True

    def is_edit_mode_active(self) -> bool:
        return bool(self.edit_mode_active)

    def is_dirty(self) -> bool:
        if not self.edit_mode_active or self.edit_buffer is None or self._original_prefab is None:
            return False
        self.sync_widgets_to_buffer()
        return self.edit_buffer != self._original_prefab

    def focused_field(self) -> str | None:
        return self._focused_field

    def last_error_message(self) -> str | None:
        return self.last_error

    def id_input(self) -> TextInput:
        return self.text_input("id")

    def text_input(self, field: str) -> TextInput:
        return self._text_inputs[str(field)]

    def text_inputs(self) -> dict[str, TextInput]:
        return dict(self._text_inputs)

    def set_button_rects(self, rects: dict[str, Rect]) -> None:
        self._button_rects = dict(rects)

    def cycle_focus_forward(self) -> None:
        self._cycle_focus(1)

    def cycle_focus_backward(self) -> None:
        self._cycle_focus(-1)

    def handle_prefab_editor_text_input(self, text: str) -> bool:
        if not self.edit_mode_active or self._focused_field not in self._text_inputs:
            return False
        widget = self._text_inputs[self._focused_field]
        changed = widget.on_text_input(text)
        if changed:
            self.sync_widgets_to_buffer()
        return bool(changed)

    def handle_prefab_editor_key(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.edit_mode_active:
            return False
        if key == optional_arcade.arcade.key.ESCAPE:
            self.cancel_edit_mode()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            widget = self._text_inputs.get(str(self._focused_field or ""))
            changed = bool(widget is not None and widget.on_key_backspace())
            if changed:
                self.sync_widgets_to_buffer()
            return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            widget = self._text_inputs.get(str(self._focused_field or ""))
            if widget is not None and widget.on_key_enter():
                widget.focused = False
                self._focused_field = None
                self.sync_widgets_to_buffer()
            return True
        if key == optional_arcade.arcade.key.TAB:
            return True
        return True

    def handle_prefab_editor_mouse_click(self, x: float, y: float) -> bool:
        overlay = self._get_overlay()
        action = self._hit_button(float(x), float(y))
        if action == "edit":
            prefab = self._overlay_selected_prefab_dict(overlay)
            if prefab is None:
                return True
            self.enter_edit_mode(prefab)
            return True
        if action == "cancel":
            self.cancel_edit_mode()
            return True
        if action == "save":
            all_prefabs = self._overlay_all_prefab_dicts(overlay)
            target = self._prefabs_target_path()
            ok = self.commit_save(all_prefabs, target)
            if ok:
                reload_model = getattr(overlay, "reload_model", None)
                if callable(reload_model):
                    reload_model()
            return True

        if self.edit_mode_active:
            clicked_field = None
            clicker = getattr(overlay, "try_click_widget", None) if overlay is not None else None
            if callable(clicker):
                clicked_field = clicker(float(x), float(y))
            if clicked_field in self._text_inputs:
                self._focus_field(str(clicked_field))
                self.sync_widgets_to_buffer()
                return True
            changed = False
            for name, widget in self._text_inputs.items():
                if widget.on_mouse_press(float(x), float(y)):
                    clicked_field = name
                    changed = True
                    break
            self._focus_field(str(clicked_field) if clicked_field else None)
            return bool(changed)
        return False

    def sync_widgets_to_buffer(self) -> None:
        if self.edit_buffer is None:
            return
        self.edit_buffer["id"] = str(self._text_inputs["id"].text or "").strip()

    def _sync_widgets_from_buffer(self) -> None:
        if self.edit_buffer is None:
            return
        self._text_inputs["id"].text = str(self.edit_buffer.get("id", "") or "")

    def _cycle_focus(self, delta: int) -> None:
        if not self.edit_mode_active or self._focused_field not in _FOCUS_CYCLE:
            return
        self.sync_widgets_to_buffer()
        index = _FOCUS_CYCLE.index(self._focused_field)
        self._focus_field(_FOCUS_CYCLE[(index + int(delta)) % len(_FOCUS_CYCLE)])

    def _focus_field(self, field: str | None) -> None:
        self._focused_field = field if field in self._text_inputs else None
        for name, widget in self._text_inputs.items():
            widget.focused = name == self._focused_field

    def _hit_button(self, x: float, y: float) -> str | None:
        for action, rect in self._button_rects.items():
            if rect.contains(float(x), float(y)):
                return action
        return None

    def _get_overlay(self) -> Any | None:
        return getattr(getattr(self._editor, "window", None), "prefab_editor_overlay", None)

    def _prefabs_target_path(self) -> Path:
        from engine.editor.prefab_editor_model import DEFAULT_PREFAB_FILE_PATH

        root_getter = getattr(self._editor, "_get_repo_root", None)
        root = Path(root_getter()) if callable(root_getter) else Path.cwd()
        return root / DEFAULT_PREFAB_FILE_PATH

    def _overlay_selected_prefab_dict(self, overlay: Any | None) -> dict[str, Any] | None:
        getter = getattr(overlay, "selected_prefab_dict", None) if overlay is not None else None
        if callable(getter):
            prefab = getter()
            return copy.deepcopy(prefab) if isinstance(prefab, dict) else None
        return None

    def _overlay_all_prefab_dicts(self, overlay: Any | None) -> list[dict[str, Any]]:
        getter = getattr(overlay, "all_prefab_dicts", None) if overlay is not None else None
        if callable(getter):
            return [copy.deepcopy(prefab) for prefab in getter()]
        return []

    def _set_save_error(self, message: str) -> None:
        self.last_error = str(message or "Unable to save prefab")
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "error", None) if feedback is not None else None
        if callable(reporter):
            reporter(self.last_error)

    def _emit_feedback_info(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "info", None) if feedback is not None else None
        if callable(reporter):
            reporter(message)
