from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController, _get_path, _set_path

CHOICE_ADD_ACTION = "choice.add"


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

    def enter_edit_mode(self, record: dict[str, Any]) -> None:
        node_id = self.selected_node_id()
        script = record.get("script")
        valid_node_id = str(node_id) if isinstance(script, dict) and node_id in script else None
        self._rebuild_text_inputs(valid_node_id, record)
        super().enter_edit_mode(record)

    def cancel_edit_mode(self) -> None:
        super().cancel_edit_mode()
        self._rebuild_text_inputs(None)

    def handle_dialogue_editor_text_input(self, text: str) -> bool:
        return self.handle_text_input(text)

    def handle_dialogue_editor_key(self, key: int, modifiers: int) -> bool:
        return self.handle_key(key, modifiers)

    def handle_dialogue_editor_mouse_click(self, x: float, y: float) -> bool:
        overlay = self._get_overlay()
        if self.is_edit_mode_active():
            action_picker = getattr(overlay, "choice_action_at", None) if overlay is not None else None
            action = action_picker(float(x), float(y)) if callable(action_picker) else None
            if action == CHOICE_ADD_ACTION:
                self._add_choice()
                return True
        else:
            idx = overlay.row_index_at(float(x), float(y)) if overlay is not None else None
            if idx is not None:
                overlay.set_selected_index(int(idx))
                return True
            node_picker = getattr(overlay, "node_id_at", None) if overlay is not None else None
            node_id = node_picker(float(x), float(y)) if callable(node_picker) else None
            if node_id is not None:
                overlay.set_selected_node_id(node_id)
                return True
        return self.handle_mouse_click(float(x), float(y))

    def _copy_record(self, record: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(record)

    def field_value(self, field: str) -> Any:
        return self._get_field_value(self.edit_buffer, field) if self.edit_buffer is not None else None

    def selected_node_id(self) -> str | None:
        overlay = self._get_overlay()
        node_getter = getattr(overlay, "selected_node_id", None) if overlay is not None else None
        node_id = node_getter() if callable(node_getter) else None
        return str(node_id) if node_id else None

    def _get_field_value(self, record: dict[str, Any], field: str) -> Any:
        return _get_path(record, field) if "." in str(field) else record.get(field)

    def _set_field_value(self, record: dict[str, Any], field: str, value: Any) -> None:
        text = str(value or "")
        if "." in str(field):
            _set_path(record, field, text)
            return
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

    def _rebuild_text_inputs(self, node_id: str | None, record: dict[str, Any] | None = None) -> None:
        from engine.ui_overlays.widgets import TextInput  # noqa: PLC0415

        record = record if isinstance(record, dict) else self.edit_buffer
        specs = list(self.TEXT_INPUT_SPECS)
        if node_id is not None:
            specs.extend(
                [
                    (f"script.{node_id}.speaker", "speaker"),
                    (f"script.{node_id}.text", "text"),
                ]
            )
            script = record.get("script") if isinstance(record, dict) else None
            node = script.get(node_id) if isinstance(script, dict) else None
            choices = node.get("choices") if isinstance(node, dict) else None
            if isinstance(choices, list):
                for i, choice in enumerate(choices):
                    if not isinstance(choice, dict):
                        continue
                    choice_prefix = f"script.{node_id}.choices.{i}"
                    specs.extend(
                        [
                            (f"{choice_prefix}.text", f"Choice {i} text"),
                            (f"{choice_prefix}.next", f"Choice {i} next"),
                        ]
                    )
        self._text_inputs = {
            field: TextInput(text="", placeholder=placeholder, focused=False, font_size=12, height=18.0)
            for field, placeholder in specs
        }

    def _add_choice(self) -> bool:
        if not self.edit_mode_active or not isinstance(self.edit_buffer, dict):
            return False
        node_id = self.selected_node_id()
        script = self.edit_buffer.get("script")
        node = script.get(node_id) if isinstance(script, dict) and node_id in script else None
        choices = node.get("choices") if isinstance(node, dict) else None
        if not isinstance(choices, list):
            return False
        self.sync_widgets_to_buffer()
        choices.append({"next": "", "text": ""})
        new_index = len(choices) - 1
        self._rebuild_text_inputs(node_id, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"script.{node_id}.choices.{new_index}.text")
        return True

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
