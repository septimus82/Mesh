from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController, _get_path, _set_path

_OPTIONAL_SCALAR_FIELDS = ("description", "type", "start_toast", "complete_toast")
STAGE_ADD_ACTION = "stage.add"
STAGE_DELETE_ACTION = "stage.delete"
STAGE_MOVE_UP_ACTION = "stage.move_up"
STAGE_MOVE_DOWN_ACTION = "stage.move_down"


class EditorQuestEditorController(EditorDatabaseFormController):
    """Edit-mode controller for the Quest Editor dock tab."""

    FORM_NAME = "Quest"
    OVERLAY_ATTR = "quest_editor_overlay"
    SAVE_SUCCESS_MESSAGE = "Quest saved"
    SAVE_ERROR_FALLBACK = "Unable to save quest"
    ID_FIELD = "id"
    FOCUS_CYCLE = ("id", "title", "description", "type", "start_toast", "complete_toast")
    TEXT_INPUT_SPECS = (
        ("id", "quest_id"),
        ("title", "Quest title"),
        ("description", "Description"),
        ("type", "type"),
        ("start_toast", "Start toast"),
        ("complete_toast", "Complete toast"),
    )

    def enter_edit_mode(self, record: dict[str, Any]) -> None:
        stage_index = self._selected_stage_index(record)
        self._rebuild_text_inputs(stage_index, record)
        super().enter_edit_mode(record)

    def cancel_edit_mode(self) -> None:
        super().cancel_edit_mode()
        self._rebuild_text_inputs(None)

    def handle_quest_editor_text_input(self, text: str) -> bool:
        return self.handle_text_input(text)

    def handle_quest_editor_key(self, key: int, modifiers: int) -> bool:
        return self.handle_key(key, modifiers)

    def handle_quest_editor_mouse_click(self, x: float, y: float) -> bool:
        if not self.is_edit_mode_active():
            overlay = self._get_overlay()
            idx = overlay.row_index_at(float(x), float(y)) if overlay is not None else None
            if idx is not None:
                overlay.set_selected_index(int(idx))
                return True
            stage_picker = getattr(overlay, "stage_id_at", None) if overlay is not None else None
            stage_id = stage_picker(float(x), float(y)) if callable(stage_picker) else None
            if stage_id is not None:
                overlay.set_selected_stage_id(stage_id)
                return True
        else:
            overlay = self._get_overlay()
            stage_action_picker = getattr(overlay, "stage_action_at", None) if overlay is not None else None
            stage_action = stage_action_picker(float(x), float(y)) if callable(stage_action_picker) else None
            if stage_action == STAGE_ADD_ACTION:
                return self._add_stage()
            if stage_action == STAGE_DELETE_ACTION:
                return self._delete_stage()
            if stage_action == STAGE_MOVE_UP_ACTION:
                return self._move_stage(-1)
            if stage_action == STAGE_MOVE_DOWN_ACTION:
                return self._move_stage(1)
        return self.handle_mouse_click(float(x), float(y))

    def _copy_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(record)

    def _record_for_compare(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._strip_empty_optional_fields(self._copy_record(record))

    def _record_for_save(self, record: dict[str, Any]) -> dict[str, Any] | None:
        return self._strip_empty_optional_fields(self._copy_record(record))

    def _get_field_value(self, record: dict[str, Any], field: str) -> Any:
        return _get_path(record, field) if "." in str(field) else record.get(field)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        next_value = str(value or "")
        if "." in str(field):
            _set_path(record, field, next_value)
            return
        if field == self.ID_FIELD:
            next_value = next_value.strip()
        record[field] = next_value

    def _selected_stage_index(self, record: dict[str, Any]) -> int | None:
        overlay = self._get_overlay()
        selected_stage_getter = getattr(overlay, "selected_stage_id", None) if overlay is not None else None
        selected_stage_id = selected_stage_getter() if callable(selected_stage_getter) else None
        if not selected_stage_id:
            return None
        stages = record.get("stages")
        if not isinstance(stages, list):
            return None
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                continue
            stage_id = str(stage.get("id") or "").strip() or f"stage_{index}"
            if stage_id == str(selected_stage_id):
                return index
        return None

    def _rebuild_text_inputs(self, stage_index: int | None, record: dict[str, Any] | None = None) -> None:
        from engine.ui_overlays.widgets import TextInput  # noqa: PLC0415

        record = record if isinstance(record, dict) else self.edit_buffer
        specs = list(self.TEXT_INPUT_SPECS)
        stages = record.get("stages") if isinstance(record, dict) else None
        stage = stages[stage_index] if isinstance(stages, list) and stage_index is not None and 0 <= stage_index < len(stages) else None
        if isinstance(stage, dict):
            specs.append((f"stages.{stage_index}.title", "Stage title"))
            if "text" in stage:
                specs.append((f"stages.{stage_index}.text", "Stage text"))
        self._text_inputs = {
            field: TextInput(text="", placeholder=placeholder, focused=False, font_size=12, height=18.0)
            for field, placeholder in specs
        }

    def _add_stage(self) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        self.sync_widgets_to_buffer()
        stages = self.edit_buffer.get("stages")
        if not isinstance(stages, list):
            stages = []
            self.edit_buffer["stages"] = stages
        new_id = _next_stage_id(stages)
        new_index = len(stages)
        stages.append({"id": new_id, "title": "New stage", "text": ""})
        overlay = self._get_overlay()
        setter = getattr(overlay, "set_selected_stage_id", None) if overlay is not None else None
        if callable(setter):
            setter(new_id)
        self._rebuild_text_inputs(new_index, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"stages.{new_index}.title")
        return True

    def _delete_stage(self) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        stages = self.edit_buffer.get("stages")
        if not isinstance(stages, list):
            return False
        stage_index = self._selected_stage_index(self.edit_buffer)
        if stage_index is None or not 0 <= stage_index < len(stages):
            return False
        self.sync_widgets_to_buffer()
        del stages[stage_index]
        next_index = stage_index if stage_index < len(stages) else len(stages) - 1
        next_stage_id = _stage_id_at(stages, next_index) if next_index >= 0 else None
        overlay = self._get_overlay()
        setter = getattr(overlay, "set_selected_stage_id", None) if overlay is not None else None
        if callable(setter):
            setter(next_stage_id)
        self._rebuild_text_inputs(next_index if next_stage_id is not None else None, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(None)
        return True

    def _move_stage(self, delta: int) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        stages = self.edit_buffer.get("stages")
        if not isinstance(stages, list):
            return False
        stage_index = self._selected_stage_index(self.edit_buffer)
        if stage_index is None:
            return False
        target_index = stage_index + int(delta)
        if not 0 <= stage_index < len(stages) or not 0 <= target_index < len(stages):
            return False
        self.sync_widgets_to_buffer()
        stages[stage_index], stages[target_index] = stages[target_index], stages[stage_index]
        self._rebuild_text_inputs(target_index, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"stages.{target_index}.title")
        return True

    def _target_path(self) -> Path:
        from engine.editor.quest_editor_model import DEFAULT_QUESTS_FILE_PATH  # noqa: PLC0415

        root_getter = getattr(self._editor, "_get_repo_root", None)
        root = Path(root_getter()) if callable(root_getter) else Path.cwd()
        return root / DEFAULT_QUESTS_FILE_PATH

    def _validate_records(
        self,
        candidate: dict[str, Any],  # noqa: ARG002
        next_records: list[dict[str, Any]],
        target_path: str | Path,
    ) -> list[str]:
        from engine.editor.quest_editor_model import validate_quest_entries  # noqa: PLC0415

        return validate_quest_entries(next_records, target_path)

    def _save_records(self, records: list[dict[str, Any]], target_path: str | Path) -> None:
        from engine.editor.quest_editor_model import save_quests  # noqa: PLC0415

        save_quests(records, target_path)

    def _overlay_selected_record(self, overlay: Any | None) -> dict[str, Any] | None:
        getter = getattr(overlay, "selected_quest_dict", None) if overlay is not None else None
        if callable(getter):
            quest = getter()
            return self._copy_record(quest) if isinstance(quest, dict) else None
        return None

    def _overlay_all_records(self, overlay: Any | None) -> list[dict[str, Any]]:
        getter = getattr(overlay, "all_quest_dicts", None) if overlay is not None else None
        if callable(getter):
            return [self._copy_record(quest) for quest in getter()]
        return []

    def _strip_empty_optional_fields(self, record: dict[str, Any]) -> dict[str, Any]:
        for field in _OPTIONAL_SCALAR_FIELDS:
            value = record.get(field)
            if isinstance(value, str) and value.strip() == "":
                record.pop(field, None)
        return record


def _next_stage_id(stages: list[Any]) -> str:
    existing_ids = {
        stage_id
        for index, stage in enumerate(stages)
        if (stage_id := _stage_id_for_collision(stage, index))
    }
    candidate_index = 1
    while True:
        candidate = f"stage_{candidate_index}"
        if candidate not in existing_ids:
            return candidate
        candidate_index += 1


def _stage_id_at(stages: list[Any], index: int) -> str | None:
    if not 0 <= index < len(stages):
        return None
    return _stage_id_for_collision(stages[index], index)


def _stage_id_for_collision(stage: Any, index: int) -> str | None:
    if not isinstance(stage, dict):
        return None
    return str(stage.get("id") or "").strip() or f"stage_{index}"
