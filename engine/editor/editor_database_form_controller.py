from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


def _get_path(payload: dict[str, Any], field_path: str) -> Any:
    if not field_path:
        return None
    current: Any = payload
    for part in field_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(payload: dict[str, Any], field_path: str, value: Any) -> None:
    if not field_path:
        return
    parts = field_path.split(".")
    current: dict[str, Any] = payload
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


class EditorDatabaseFormController(ABC):
    """Shared edit-mode controller behavior for editor database forms."""

    FORM_NAME = "record"
    OVERLAY_ATTR = ""
    SAVE_SUCCESS_MESSAGE = "Saved"
    SAVE_ERROR_FALLBACK = "Unable to save"
    ID_FIELD = "id"
    FOCUS_CYCLE: tuple[str, ...] = ()
    TEXT_INPUT_SPECS: tuple[tuple[str, str], ...] = ()

    def __init__(self, editor: Any) -> None:
        from engine.ui_overlays.widgets import TextInput  # noqa: PLC0415

        self._editor = editor
        self.edit_mode_active = False
        self.edit_buffer: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._focused_field: str | None = None
        self._original_record: dict[str, Any] | None = None
        self._original_record_id: str | None = None
        self._text_inputs = {
            field: TextInput(text="", placeholder=placeholder, focused=False, font_size=12, height=18.0)
            for field, placeholder in self.TEXT_INPUT_SPECS
        }
        self._button_rects: dict[str, Any] = {}

    def enter_edit_mode(self, record: dict[str, Any]) -> None:
        editable = self._record_for_edit(record)
        self.edit_mode_active = True
        self._original_record = self._record_for_compare(editable)
        self._original_record_id = str(record.get(self.ID_FIELD, "") or "")
        self.edit_buffer = self._copy_record(editable)
        self.last_error = None
        self._focused_field = self.ID_FIELD
        self._sync_widgets_from_buffer()
        self._focus_field(self.ID_FIELD)

    def cancel_edit_mode(self) -> None:
        self.edit_mode_active = False
        self.edit_buffer = None
        self.last_error = None
        self._focused_field = None
        self._original_record = None
        self._original_record_id = None
        for widget in self._text_inputs.values():
            widget.focused = False

    def commit_save(self, all_records: list[dict[str, Any]], target_path: str | Path) -> bool:
        if not self.edit_mode_active or self.edit_buffer is None:
            return False

        self.sync_widgets_to_buffer()
        candidate = self._record_for_save(self._copy_record(self.edit_buffer))
        if candidate is None:
            return False
        original_id = str(self._original_record_id or candidate.get(self.ID_FIELD, "") or "")
        next_records = [self._copy_record(record) for record in all_records]
        replaced = False
        for index, record in enumerate(next_records):
            if str(record.get(self.ID_FIELD, "") or "") == original_id:
                next_records[index] = candidate
                replaced = True
                break
        if not replaced:
            next_records.append(candidate)

        errors = self._validate_records(candidate, next_records, target_path)
        if errors:
            self._set_save_error("; ".join(errors))
            return False
        try:
            self._save_records(next_records, target_path)
        except Exception as exc:  # noqa: BLE001  # REASON: save errors must stay visible in the form
            self._set_save_error(str(exc))
            return False

        self.cancel_edit_mode()
        self._emit_feedback_info(self.SAVE_SUCCESS_MESSAGE)
        return True

    def is_edit_mode_active(self) -> bool:
        return bool(self.edit_mode_active)

    def is_dirty(self) -> bool:
        if not self.edit_mode_active or self.edit_buffer is None or self._original_record is None:
            return False
        self.sync_widgets_to_buffer()
        return self._record_for_compare(self._copy_record(self.edit_buffer)) != self._original_record

    def focused_field(self) -> str | None:
        return self._focused_field

    def last_error_message(self) -> str | None:
        return self.last_error

    def id_input(self) -> Any:
        return self.text_input(self.ID_FIELD)

    def text_input(self, field: str) -> Any:
        return self._text_inputs[str(field)]

    def text_inputs(self) -> dict[str, Any]:
        return dict(self._text_inputs)

    def set_button_rects(self, rects: dict[str, Any]) -> None:
        self._button_rects = dict(rects)

    def cycle_focus_forward(self) -> None:
        self._cycle_focus(1)

    def cycle_focus_backward(self) -> None:
        self._cycle_focus(-1)

    def handle_text_input(self, text: str) -> bool:
        if not self.edit_mode_active or self._focused_field not in self._text_inputs:
            return False
        widget = self._text_inputs[self._focused_field]
        changed = widget.on_text_input(text)
        if changed:
            self.sync_widgets_to_buffer()
        return bool(changed)

    def handle_key(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.edit_mode_active:
            return False
        import engine.optional_arcade as optional_arcade  # noqa: PLC0415

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

    def handle_mouse_click(self, x: float, y: float) -> bool:
        overlay = self._get_overlay()
        action = self._hit_button(float(x), float(y))
        if action == "edit":
            record = self._overlay_selected_record(overlay)
            if record is None:
                return True
            self.enter_edit_mode(record)
            return True
        if action == "cancel":
            self.cancel_edit_mode()
            return True
        if action == "save":
            all_records = self._overlay_all_records(overlay)
            ok = self.commit_save(all_records, self._target_path())
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
            if self._handle_special_widget_click(clicked_field):
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
        for field, widget in self._text_inputs.items():
            self._set_field_value(self.edit_buffer, field, str(widget.text or ""))

    def _sync_widgets_from_buffer(self) -> None:
        if self.edit_buffer is None:
            return
        for field, widget in self._text_inputs.items():
            value = self._get_field_value(self.edit_buffer, field)
            widget.text = "" if value is None else str(value)

    def _cycle_focus(self, delta: int) -> None:
        if not self.edit_mode_active or self._focused_field not in self.FOCUS_CYCLE:
            return
        self.sync_widgets_to_buffer()
        index = self.FOCUS_CYCLE.index(self._focused_field)
        self._focus_field(self.FOCUS_CYCLE[(index + int(delta)) % len(self.FOCUS_CYCLE)])

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
        return getattr(getattr(self._editor, "window", None), self.OVERLAY_ATTR, None)

    def _set_save_error(self, message: str) -> None:
        self.last_error = str(message or self.SAVE_ERROR_FALLBACK)
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "error", None) if feedback is not None else None
        if callable(reporter):
            reporter(self.last_error)

    def _emit_feedback_info(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "info", None) if feedback is not None else None
        if callable(reporter):
            reporter(message)

    def _copy_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return dict(record)

    def _record_for_edit(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._copy_record(record)

    def _record_for_compare(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._copy_record(record)

    def _record_for_save(self, record: dict[str, Any]) -> dict[str, Any] | None:
        return record

    def _get_field_value(self, record: dict[str, Any], field: str) -> Any:
        return record.get(field)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        record[field] = value

    def _handle_special_widget_click(self, clicked_field: str | None) -> bool:  # noqa: ARG002
        return False

    @abstractmethod
    def _target_path(self) -> Path:
        raise NotImplementedError

    @abstractmethod
    def _validate_records(
        self,
        candidate: dict[str, Any],
        next_records: list[dict[str, Any]],
        target_path: str | Path,
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def _save_records(self, records: list[dict[str, Any]], target_path: str | Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def _overlay_selected_record(self, overlay: Any | None) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def _overlay_all_records(self, overlay: Any | None) -> list[dict[str, Any]]:
        raise NotImplementedError
