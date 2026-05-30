"""Read-only dialogue editor model helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_DIALOGUES_FILE_PATH: Path = Path("assets") / "data" / "dialogues.json"

DIALOGUE_SCALAR_FIELD_ORDER: tuple[str, ...] = ("id", "schema_version", "start_node")


class DialogueEditorModel:
    """Read-only view model for browsing assets/data/dialogues.json."""

    def __init__(self, data_path: Path | None = None) -> None:
        self._data_path = Path(data_path) if data_path is not None else DEFAULT_DIALOGUES_FILE_PATH
        self._dialogues: list[dict[str, Any]] = []
        self._selected_index = 0

    @classmethod
    def load(cls, data_path: Path | None = None) -> "DialogueEditorModel":
        model = cls(data_path)
        model.reload()
        return model

    def reload(self) -> None:
        try:
            from engine import json_io  # noqa: PLC0415

            payload = json_io.read_json(self._data_path)
        except Exception:  # noqa: BLE001  # REASON: editor browsing should degrade to an empty list on malformed local content
            payload = {}
        raw_dialogues = payload.get("dialogues") if isinstance(payload, dict) else None
        self._dialogues = [dict(entry) for entry in raw_dialogues or [] if isinstance(entry, dict)] if isinstance(raw_dialogues, list) else []
        self._selected_index = self._clamp_index(self._selected_index)

    def dialogues(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._dialogues]

    @property
    def dialogue_count(self) -> int:
        return len(self._dialogues)

    def selected_index(self) -> int:
        self._selected_index = self._clamp_index(self._selected_index)
        return self._selected_index

    def set_selected_index(self, index: int) -> bool:
        next_index = self._clamp_index(index)
        changed = next_index != self._selected_index
        self._selected_index = next_index
        return changed

    def selected_dialogue(self) -> dict[str, Any] | None:
        if not self._dialogues:
            self._selected_index = 0
            return None
        return dict(self._dialogues[self.selected_index()])

    def list_rows(self) -> list[tuple[str, str, str]]:
        rows: list[tuple[str, str, str]] = []
        for dialogue in self._dialogues:
            dialogue_id = _string_value(dialogue.get("id"))
            start_node = _string_value(dialogue.get("start_node"))
            rows.append((dialogue_id, start_node, str(_node_count(dialogue))))
        return rows

    def detail_rows(self, index: int | None = None) -> list[tuple[str, str]]:
        dialogue = self._dialogue_at(index)
        if dialogue is None:
            return []
        return [
            ("ID", _string_value(dialogue.get("id"))),
            ("Schema version", _string_value(dialogue.get("schema_version"))),
            ("Start node", _string_value(dialogue.get("start_node"))),
            ("Node count", str(_node_count(dialogue))),
            ("Choice count", str(_choice_count(dialogue))),
        ]

    def scalar_detail_rows(self) -> list[tuple[str, str, str]]:
        dialogue = self.selected_dialogue()
        if dialogue is None:
            return []
        rows: list[tuple[str, str, str]] = []
        for field_path in DIALOGUE_SCALAR_FIELD_ORDER:
            value = dialogue.get(field_path)
            if value is None or value == "":
                continue
            rows.append((_label_for_field(field_path), _format_value(value), field_path))
        return rows

    def _dialogue_at(self, index: int | None) -> dict[str, Any] | None:
        if not self._dialogues:
            return None
        if index is None:
            index = self.selected_index()
        index = max(0, min(int(index), len(self._dialogues) - 1))
        return dict(self._dialogues[index])

    def _clamp_index(self, index: int) -> int:
        if not self._dialogues:
            return 0
        return max(0, min(int(index), len(self._dialogues) - 1))


def _node_count(dialogue: dict[str, Any]) -> int:
    script = dialogue.get("script")
    return len(script) if isinstance(script, dict) else 0


def _choice_count(dialogue: dict[str, Any]) -> int:
    script = dialogue.get("script")
    if not isinstance(script, dict):
        return 0
    count = 0
    for node in script.values():
        if not isinstance(node, dict):
            continue
        choices = node.get("choices")
        if isinstance(choices, list):
            count += len(choices)
    return count


def script_rows(dialogue: dict[str, Any]) -> list[tuple[str, str]]:
    script = dialogue.get("script")
    if not isinstance(script, dict):
        return []
    rows: list[tuple[str, str]] = []
    for node_id, node in script.items():
        if not isinstance(node, dict):
            continue
        node_next = node.get("next")
        if isinstance(node_next, str) and node_next.strip():
            summary = f"-> {node_next.strip()}"
        else:
            choices = node.get("choices")
            if isinstance(choices, list):
                choice_count = len(choices)
                summary = "1 choice" if choice_count == 1 else f"{choice_count} choices"
            else:
                summary = "(end)"
        rows.append((str(node_id), summary))
    return rows


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _label_for_field(field_path: str) -> str:
    return {
        "id": "ID",
        "schema_version": "Schema version",
        "start_node": "Start node",
    }.get(field_path, field_path)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def validate_dialogue_entries(entries: list[dict[str, Any]], target_path: str | Path) -> list[str]:  # noqa: ARG001
    """Return validation error messages for editable dialogue payloads."""
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index}: must be a dict")
            continue
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            errors.append(f"entry {index}: id must be a non-empty string")
            continue
        entry_id_norm = entry_id.strip()
        if entry_id_norm in seen_ids:
            errors.append(f"duplicate dialogue id '{entry_id_norm}'")
        else:
            seen_ids.add(entry_id_norm)
        schema_version = entry.get("schema_version")
        if schema_version is not None:
            if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version <= 0:
                errors.append(
                    f"entry '{entry_id_norm}': schema_version must be a positive integer, got {schema_version!r}"
                )
        start_node = entry.get("start_node")
        script = entry.get("script")
        node_keys = set(script.keys()) if isinstance(script, dict) else set()
        if start_node is not None and isinstance(start_node, str) and start_node.strip():
            if start_node.strip() not in node_keys:
                errors.append(
                    f"entry '{entry_id_norm}': start_node '{start_node.strip()}' does not exist in script"
                )
        errors.extend(_dialogue_reference_errors(entry_id_norm, script, node_keys))
    return errors


def dialogue_reference_problem_count(dialogue: dict[str, Any]) -> int:
    if not isinstance(dialogue, dict):
        return 0
    entry_id_norm = _string_value(dialogue.get("id"))
    script = dialogue.get("script")
    node_keys = set(script.keys()) if isinstance(script, dict) else set()
    return len(_dialogue_reference_errors(entry_id_norm, script, node_keys))


def _dialogue_reference_errors(entry_id_norm: str, script: Any, node_keys: set[str]) -> list[str]:
    errors: list[str] = []
    if isinstance(script, dict):
        for node_id, node in script.items():
            if not isinstance(node, dict):
                continue
            node_next = node.get("next")
            if isinstance(node_next, str) and node_next.strip() and node_next.strip() not in node_keys:
                errors.append(
                    f"entry '{entry_id_norm}': node '{node_id}' next '{node_next.strip()}' does not exist in script"
                )
            choices = node.get("choices")
            if isinstance(choices, list):
                for i, choice in enumerate(choices):
                    if not isinstance(choice, dict):
                        continue
                    choice_next = choice.get("next")
                    if isinstance(choice_next, str) and choice_next.strip() and choice_next.strip() not in node_keys:
                        errors.append(
                            f"entry '{entry_id_norm}': node '{node_id}' choice {i} next '{choice_next.strip()}' does not exist in script"
                        )
                    choice_text = choice.get("text")
                    if not isinstance(choice_text, str) or not choice_text.strip():
                        errors.append(
                            f"entry '{entry_id_norm}': node '{node_id}' choice {i} text is empty"
                        )
    return errors


def save_dialogues(entries: list[dict[str, Any]], target_path: str | Path) -> None:
    """Persist dialogue dictionaries to assets/data/dialogues.json shape."""
    from engine.persistence_io import write_json_atomic  # noqa: PLC0415

    errors = validate_dialogue_entries(entries, target_path)
    if errors:
        raise ValueError("; ".join(errors))
    write_json_atomic(Path(target_path), {"dialogues": entries}, sort_keys=False, trailing_newline=True)
