"""Read-only dialogue editor model helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_DIALOGUES_FILE_PATH: Path = Path("assets") / "data" / "dialogues.json"


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


def _string_value(value: Any) -> str:
    return str(value or "").strip()
