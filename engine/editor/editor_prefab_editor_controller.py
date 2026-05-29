from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController, _get_path, _set_path  # noqa: F401


class EditorPrefabEditorController(EditorDatabaseFormController):
    """Edit-mode controller for the Prefab Editor dock tab."""

    FORM_NAME = "Prefab"
    OVERLAY_ATTR = "prefab_editor_overlay"
    SAVE_SUCCESS_MESSAGE = "Prefab saved"
    SAVE_ERROR_FALLBACK = "Unable to save prefab"
    ID_FIELD = "id"
    FOCUS_CYCLE = ("id", "display_name", "entity.sprite", "entity.encounter_cost")
    TEXT_INPUT_SPECS = (
        ("id", "prefab_id"),
        ("display_name", "Display name"),
        ("entity.sprite", "assets/..."),
        ("entity.encounter_cost", "1"),
    )

    def handle_prefab_editor_text_input(self, text: str) -> bool:
        return self.handle_text_input(text)

    def handle_prefab_editor_key(self, key: int, modifiers: int) -> bool:
        return self.handle_key(key, modifiers)

    def handle_prefab_editor_mouse_click(self, x: float, y: float) -> bool:
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
        candidate = self._copy_record(record)
        self._coerce_encounter_cost_for_compare(candidate)
        return candidate

    def _record_for_save(self, record: dict[str, Any]) -> dict[str, Any] | None:
        candidate = self._copy_record(record)
        if not self._coerce_encounter_cost(candidate):
            return None
        return candidate

    def _get_field_value(self, record: dict[str, Any], field: str) -> Any:
        return _get_path(record, field)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        next_value = str(value or "")
        if field == "id":
            next_value = next_value.strip()
        _set_path(record, field, next_value)

    def _target_path(self) -> Path:
        from engine.editor.prefab_editor_model import DEFAULT_PREFAB_FILE_PATH  # noqa: PLC0415

        root_getter = getattr(self._editor, "_get_repo_root", None)
        root = Path(root_getter()) if callable(root_getter) else Path.cwd()
        return root / DEFAULT_PREFAB_FILE_PATH

    def _validate_records(
        self,
        candidate: dict[str, Any],  # noqa: ARG002
        next_records: list[dict[str, Any]],
        target_path: str | Path,
    ) -> list[str]:
        from engine.editor.prefab_editor_model import validate_prefab_entries  # noqa: PLC0415

        return validate_prefab_entries(next_records, target_path)

    def _save_records(self, records: list[dict[str, Any]], target_path: str | Path) -> None:
        from engine.editor.prefab_editor_model import save_prefabs  # noqa: PLC0415

        save_prefabs(records, target_path)

    def _overlay_selected_record(self, overlay: Any | None) -> dict[str, Any] | None:
        getter = getattr(overlay, "selected_prefab_dict", None) if overlay is not None else None
        if callable(getter):
            prefab = getter()
            return self._copy_record(prefab) if isinstance(prefab, dict) else None
        return None

    def _overlay_all_records(self, overlay: Any | None) -> list[dict[str, Any]]:
        getter = getattr(overlay, "all_prefab_dicts", None) if overlay is not None else None
        if callable(getter):
            return [self._copy_record(prefab) for prefab in getter()]
        return []

    def _coerce_encounter_cost(self, candidate: dict[str, Any]) -> bool:
        value = _get_path(candidate, "entity.encounter_cost")
        if isinstance(value, str):
            stripped = value.strip()
            entity = candidate.get("entity")
            if stripped == "":
                if isinstance(entity, dict):
                    entity.pop("encounter_cost", None)
                return True
            try:
                _set_path(candidate, "entity.encounter_cost", int(stripped))
            except ValueError:
                self._set_save_error("entity.encounter_cost must be an integer")
                return False
        return True

    def _coerce_encounter_cost_for_compare(self, candidate: dict[str, Any]) -> None:
        value = _get_path(candidate, "entity.encounter_cost")
        if not isinstance(value, str):
            return
        stripped = value.strip()
        entity = candidate.get("entity")
        if stripped == "":
            if isinstance(entity, dict):
                entity.pop("encounter_cost", None)
            return
        try:
            _set_path(candidate, "entity.encounter_cost", int(stripped))
        except ValueError:
            return
