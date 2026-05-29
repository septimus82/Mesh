from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController

_OPTIONAL_SCALAR_FIELDS = ("description", "type", "start_toast", "complete_toast")


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
        return self.handle_mouse_click(float(x), float(y))

    def _copy_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(record)

    def _record_for_compare(self, record: dict[str, Any]) -> dict[str, Any]:
        return self._strip_empty_optional_fields(self._copy_record(record))

    def _record_for_save(self, record: dict[str, Any]) -> dict[str, Any] | None:
        return self._strip_empty_optional_fields(self._copy_record(record))

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        next_value = str(value or "")
        if field == self.ID_FIELD:
            next_value = next_value.strip()
        record[field] = next_value

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
