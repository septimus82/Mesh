from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController


class EditorDialogueEditorController(EditorDatabaseFormController):
    """Edit-mode controller for the Dialogue Editor dock tab."""

    FORM_NAME = "Dialogue"
    OVERLAY_ATTR = "dialogue_editor_overlay"
    SAVE_SUCCESS_MESSAGE = "Dialogue saved"
    SAVE_ERROR_FALLBACK = "Unable to save dialogue"
    ID_FIELD = "id"
    FOCUS_CYCLE: tuple[str, ...] = ("id", "schema_version", "start_node")
    TEXT_INPUT_SPECS: tuple[tuple[str, str], ...] = (
        ("id", "dialogue_id"),
        ("schema_version", "schema_version"),
        ("start_node", "start_node"),
    )

    def handle_dialogue_editor_text_input(self, text: str) -> bool:
        return self.handle_text_input(text)

    def handle_dialogue_editor_key(self, key: int, modifiers: int) -> bool:
        return self.handle_key(key, modifiers)

    def handle_dialogue_editor_mouse_click(self, x: float, y: float) -> bool:
        if not self.is_edit_mode_active():
            overlay = self._get_overlay()
            idx = overlay.row_index_at(float(x), float(y)) if overlay is not None else None
            if idx is not None:
                overlay.set_selected_index(int(idx))
                return True
        return self.handle_mouse_click(float(x), float(y))

    def _copy_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(record)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        text = str(value or "")
        if field == "schema_version":
            if text == "":
                record.pop("schema_version", None)
                return
            try:
                record["schema_version"] = int(text)
            except ValueError:
                record["schema_version"] = text  # let validator reject non-int
            return
        if field == self.ID_FIELD:
            text = text.strip()
        record[field] = text

    def _target_path(self) -> Path:
        from engine.editor.dialogue_editor_model import DEFAULT_DIALOGUES_FILE_PATH  # noqa: PLC0415

        root_getter = getattr(self._editor, "_get_repo_root", None)
        root = Path(root_getter()) if callable(root_getter) else Path.cwd()
        return root / DEFAULT_DIALOGUES_FILE_PATH

    def _validate_records(
        self,
        candidate: dict[str, Any],  # noqa: ARG002
        next_records: list[dict[str, Any]],
        target_path: str | Path,
    ) -> list[str]:
        from engine.editor.dialogue_editor_model import validate_dialogue_entries  # noqa: PLC0415

        return validate_dialogue_entries(next_records, target_path)

    def _save_records(self, records: list[dict[str, Any]], target_path: str | Path) -> None:
        from engine.editor.dialogue_editor_model import save_dialogues  # noqa: PLC0415

        save_dialogues(records, target_path)

    def _overlay_selected_record(self, overlay: Any | None) -> dict[str, Any] | None:
        getter = getattr(overlay, "selected_dialogue_dict", None) if overlay is not None else None
        if callable(getter):
            dialogue = getter()
            return self._copy_record(dialogue) if isinstance(dialogue, dict) else None
        return None

    def _overlay_all_records(self, overlay: Any | None) -> list[dict[str, Any]]:
        getter = getattr(overlay, "all_dialogue_dicts", None) if overlay is not None else None
        if callable(getter):
            return [self._copy_record(d) for d in getter()]
        return []
