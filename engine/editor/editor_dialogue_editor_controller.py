from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from engine.editor.editor_database_form_controller import EditorDatabaseFormController, _get_path, _set_path

CHOICE_ADD_ACTION = "choice.add"
NODE_ADD_ACTION = "node.add"
NODE_DELETE_ACTION = "node.delete"
_CHOICE_ACTION_PREFIX = "choice."


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
            choice_action = _choice_action_parts(action)
            if choice_action is not None:
                choice_index, choice_verb = choice_action
                if choice_verb == "delete":
                    self._delete_choice(choice_index)
                    return True
                if choice_verb == "move_up":
                    self._move_choice(choice_index, -1)
                    return True
                if choice_verb == "move_down":
                    self._move_choice(choice_index, 1)
                    return True
            node_action_picker = getattr(overlay, "node_action_at", None) if overlay is not None else None
            node_action = node_action_picker(float(x), float(y)) if callable(node_action_picker) else None
            if node_action == NODE_ADD_ACTION:
                self._add_node()
                return True
            if node_action == NODE_DELETE_ACTION:
                self._delete_node()
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
            script = record.get("script") if isinstance(record, dict) else None
            node = script.get(node_id) if isinstance(script, dict) else None
            specs.extend(
                [
                    (f"script.{node_id}.speaker", "speaker"),
                    (f"script.{node_id}.text", "text"),
                ]
            )
            if isinstance(node, dict) and not node.get("choices"):
                specs.append((f"script.{node_id}.next", "next"))
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
        if not isinstance(node, dict):
            return False
        self.sync_widgets_to_buffer()
        choices = node.get("choices")
        if not isinstance(choices, list):
            choices = []
            node["choices"] = choices
        if len(choices) == 0:
            node["next"] = ""
        choices.append({"next": "", "text": ""})
        new_index = len(choices) - 1
        self._rebuild_text_inputs(node_id, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"script.{node_id}.choices.{new_index}.text")
        return True

    def _delete_choice(self, index: int) -> bool:
        if not self.edit_mode_active or not isinstance(self.edit_buffer, dict):
            return False
        node_id = self.selected_node_id()
        script = self.edit_buffer.get("script")
        node = script.get(node_id) if isinstance(script, dict) and node_id in script else None
        choices = node.get("choices") if isinstance(node, dict) else None
        if not isinstance(choices, list) or not 0 <= int(index) < len(choices):
            return False
        self.sync_widgets_to_buffer()
        del choices[int(index)]
        if not choices:
            del node["choices"]
        self._rebuild_text_inputs(node_id, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(None)
        return True

    def _move_choice(self, index: int, delta: int) -> bool:
        if not self.edit_mode_active or not isinstance(self.edit_buffer, dict):
            return False
        node_id = self.selected_node_id()
        script = self.edit_buffer.get("script")
        node = script.get(node_id) if isinstance(script, dict) and node_id in script else None
        choices = node.get("choices") if isinstance(node, dict) else None
        target = int(index) + int(delta)
        if not isinstance(choices, list) or not 0 <= int(index) < len(choices) or not 0 <= target < len(choices):
            return False
        self.sync_widgets_to_buffer()
        choices[int(index)], choices[target] = choices[target], choices[int(index)]
        self._rebuild_text_inputs(node_id, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"script.{node_id}.choices.{target}.text")
        return True

    def _add_node(self) -> bool:
        if not self.edit_mode_active or not isinstance(self.edit_buffer, dict):
            return False
        script = self.edit_buffer.get("script")
        if not isinstance(script, dict):
            return False
        self.sync_widgets_to_buffer()
        new_id = _next_node_id(script)
        script[new_id] = {"speaker": "", "text": "", "next": ""}
        overlay = self._get_overlay()
        selector = getattr(overlay, "set_selected_node_id", None) if overlay is not None else None
        if callable(selector):
            selector(new_id)
        self._rebuild_text_inputs(new_id, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(f"script.{new_id}.speaker")
        return True

    def _delete_node(self) -> bool:
        if not self.edit_mode_active or not isinstance(self.edit_buffer, dict):
            return False
        script = self.edit_buffer.get("script")
        node_id = self.selected_node_id()
        if not isinstance(script, dict) or node_id not in script:
            return False
        self.sync_widgets_to_buffer()
        del script[node_id]
        next_id = _reconciled_node_id(script, self.edit_buffer.get("start_node"))
        overlay = self._get_overlay()
        selector = getattr(overlay, "set_selected_node_id", None) if overlay is not None else None
        if callable(selector):
            selector(next_id)
        self._rebuild_text_inputs(next_id, self.edit_buffer)
        self._sync_widgets_from_buffer()
        self._focus_field(None)
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


def _choice_delete_index(action: object) -> int | None:
    parts = _choice_action_parts(action)
    if parts is None or parts[1] != "delete":
        return None
    return parts[0]


def _choice_action_parts(action: object) -> tuple[int, str] | None:
    text = str(action or "")
    if not text.startswith(_CHOICE_ACTION_PREFIX):
        return None
    pieces = text[len(_CHOICE_ACTION_PREFIX) :].split(".")
    if len(pieces) != 2 or not pieces[0].isdigit() or not pieces[1]:
        return None
    return int(pieces[0]), pieces[1]


def _next_node_id(script: dict[str, Any]) -> str:
    index = 1
    while f"node_{index}" in script:
        index += 1
    return f"node_{index}"


def _reconciled_node_id(script: dict[str, Any], start_node: object) -> str | None:
    start = str(start_node or "").strip()
    return start if start in script else (next(iter(script)) if script else None)
