from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController, _get_path, _set_path  # noqa: F401
from engine.editor.prefab_editor_model import PREFAB_LIST_COMPLEX_FIELDS

_BEHAVIOUR_FIELD_PREFIX = "entity.behaviours."
PREFAB_DICT_COMPLEX_FIELDS = ("metadata", "entity.behaviour_config")


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

    def __init__(self, editor: Any) -> None:
        super().__init__(editor)
        self._warned_unknown_behaviours: set[tuple[str, str]] = set()

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
        else:
            overlay = self._get_overlay()
            action_at = getattr(overlay, "complex_entry_action_at", None) if overlay is not None else None
            action = action_at(float(x), float(y)) if callable(action_at) else None
            add_field_path = _complex_list_add_action(action)
            if add_field_path is not None:
                return self._add_list_entry(add_field_path)
            parsed_action = _complex_list_action_parts(action)
            if parsed_action is not None:
                field_path, index, verb = parsed_action
                if verb == "delete":
                    return self._delete_list_entry(field_path, index)
                if verb == "move_up":
                    return self._move_list_entry(field_path, index, -1)
                if verb == "move_down":
                    return self._move_list_entry(field_path, index, 1)
            parsed_dict_action = _complex_dict_action_parts(action)
            if parsed_dict_action is not None:
                field_path, key, verb = parsed_dict_action
                if verb == "delete":
                    return self._delete_dict_entry(field_path, key)
        return self.handle_mouse_click(float(x), float(y))

    def enter_edit_mode(self, record: dict[str, Any]) -> None:
        self._warned_unknown_behaviours.clear()
        self._rebuild_text_inputs(record)
        super().enter_edit_mode(record)

    def cancel_edit_mode(self) -> None:
        super().cancel_edit_mode()
        self._warned_unknown_behaviours.clear()
        self._rebuild_text_inputs(None)

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
        if _is_prefab_list_entry_field(field):
            if next_value == "":
                self._set_save_error(f"{field} cannot be empty")
                return
            _set_path(record, field, next_value)
            if field.startswith(_BEHAVIOUR_FIELD_PREFIX):
                self._warn_for_unknown_behaviour(field, next_value)
            return
        _set_path(record, field, next_value)

    def _rebuild_text_inputs(self, record: dict[str, Any] | None) -> None:
        from engine.ui_overlays.widgets import TextInput  # noqa: PLC0415

        specs = list(self.TEXT_INPUT_SPECS)
        if isinstance(record, dict):
            for field_path in PREFAB_LIST_COMPLEX_FIELDS:
                value = _get_path(record, field_path)
                if isinstance(value, list):
                    specs.extend(
                        (f"{field_path}.{index}", f"{_list_entry_placeholder(field_path)} {index}")
                        for index, item in enumerate(value)
                        if isinstance(item, str)
                    )
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

    def _delete_list_entry(self, field_path: str, index: int) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        if field_path not in PREFAB_LIST_COMPLEX_FIELDS:
            return False
        self.sync_widgets_to_buffer()
        items = _get_path(self.edit_buffer, field_path)
        if not isinstance(items, list) or not 0 <= int(index) < len(items):
            return False
        items.pop(int(index))
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        return True

    def _delete_dict_entry(self, field_path: str, key: str) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        if field_path not in PREFAB_DICT_COMPLEX_FIELDS:
            return False
        self.sync_widgets_to_buffer()
        mapping = _get_path(self.edit_buffer, field_path)
        if not isinstance(mapping, dict) or key not in mapping:
            return False
        del mapping[key]
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        return True

    def _move_list_entry(self, field_path: str, index: int, delta: int) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        if field_path not in PREFAB_LIST_COMPLEX_FIELDS:
            return False
        self.sync_widgets_to_buffer()
        items = _get_path(self.edit_buffer, field_path)
        source = int(index)
        target = source + int(delta)
        if not isinstance(items, list) or not 0 <= source < len(items) or not 0 <= target < len(items):
            return False
        items[source], items[target] = items[target], items[source]
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"{field_path}.{target}")
        return True

    def _add_list_entry(self, field_path: str) -> bool:
        if not self.is_edit_mode_active() or not isinstance(self.edit_buffer, dict):
            return False
        if field_path not in PREFAB_LIST_COMPLEX_FIELDS:
            return False
        self.sync_widgets_to_buffer()
        items = _get_path(self.edit_buffer, field_path)
        if not isinstance(items, list):
            _set_path(self.edit_buffer, field_path, [])
            items = _get_path(self.edit_buffer, field_path)
        if not isinstance(items, list):
            return False
        new_index = len(items)
        seed = _list_entry_seed(field_path)
        items.append(seed)
        if field_path == "entity.behaviours":
            self._warned_unknown_behaviours.add((f"{field_path}.{new_index}", seed))
        self._rebuild_text_inputs(self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"{field_path}.{new_index}")
        return True

    def _warn_for_unknown_behaviour(self, field: str, value: str) -> None:
        known = _known_behaviour_names()
        if not known or value in known:
            return
        warning_key = (field, value)
        if warning_key in self._warned_unknown_behaviours:
            return
        self._warned_unknown_behaviours.add(warning_key)
        self._emit_feedback_warning(f"Unknown prefab behaviour '{value}'")

    def _emit_feedback_warning(self, message: str) -> None:
        feedback = getattr(self._editor, "feedback", None)
        reporter = getattr(feedback, "warning", None) if feedback is not None else None
        if not callable(reporter):
            reporter = getattr(feedback, "info", None) if feedback is not None else None
        if callable(reporter):
            reporter(message)

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


def _complex_list_add_action(action: object) -> str | None:
    parts = str(action or "").split("#")
    if len(parts) != 2:
        return None
    field_path, verb = parts
    if verb != "add" or field_path not in PREFAB_LIST_COMPLEX_FIELDS:
        return None
    return field_path


def _complex_list_action_parts(action: object) -> tuple[str, int, str] | None:
    parts = str(action or "").split("#")
    if len(parts) != 3:
        return None
    field_path, index_text, verb = parts
    if field_path not in PREFAB_LIST_COMPLEX_FIELDS:
        return None
    if not index_text.isdigit() or not verb:
        return None
    return field_path, int(index_text), verb


def _complex_dict_action_parts(action: object) -> tuple[str, str, str] | None:
    text = str(action or "")
    for field_path in PREFAB_DICT_COMPLEX_FIELDS:
        prefix = f"{field_path}#"
        if not text.startswith(prefix):
            continue
        tail = text.removeprefix(prefix)
        key, separator, verb = tail.rpartition("#")
        if not separator or not key or not verb:
            return None
        return field_path, key, verb
    return None


def _is_prefab_list_entry_field(field: str) -> bool:
    for field_path in PREFAB_LIST_COMPLEX_FIELDS:
        prefix = f"{field_path}."
        if field.startswith(prefix):
            index_text = field.removeprefix(prefix)
            return index_text.isdigit()
    return False


def _list_entry_placeholder(field_path: str) -> str:
    return {
        "tags": "Tag",
        "require_flags": "Require flag",
        "forbid_flags": "Forbid flag",
        "entity.behaviours": "Behaviour",
        "entity.require_flags": "Entity require flag",
    }.get(field_path, field_path)


def _list_entry_seed(field_path: str) -> str:
    if field_path == "tags":
        return "new_tag"
    if field_path == "entity.behaviours":
        return "NewBehaviour"
    return "new_flag"


def _known_behaviour_names() -> frozenset[str]:
    try:
        from engine.behaviours import BEHAVIOUR_REGISTRY, load_builtin_behaviours  # noqa: PLC0415

        load_builtin_behaviours()
        return frozenset(
            str(name).strip()
            for name in BEHAVIOUR_REGISTRY
            if isinstance(name, str) and str(name).strip()
        )
    except Exception:  # noqa: BLE001  # REASON: behaviour registry may be unavailable in editor tests/runtime
        return frozenset()
