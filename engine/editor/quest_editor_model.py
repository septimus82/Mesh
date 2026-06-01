"""Read-only quest editor model helpers."""

from __future__ import annotations

import json
from json import dumps as _format_structured_value
from pathlib import Path
from typing import Any

DEFAULT_QUESTS_FILE_PATH: Path = Path("assets") / "data" / "quests.json"

QUEST_SCALAR_FIELD_ORDER: tuple[str, ...] = (
    "id",
    "title",
    "description",
    "type",
    "start_toast",
    "complete_toast",
)

QUEST_COMPLEX_FIELD_ORDER: tuple[str, ...] = (
    "stages",
    "steps",
    "reward",
    "requires_flags",
    "blocks_flags",
)


class QuestEditorModel:
    """Read-only view model for authoring quests from assets/data/quests.json.

    The editor reads quest JSON directly. Runtime QuestManager and QuestRunner
    instances keep their own state and remain stale until their reload paths run.
    """

    def __init__(self, data_path: Path | None = None) -> None:
        self._data_path = Path(data_path) if data_path is not None else DEFAULT_QUESTS_FILE_PATH
        self._quests: list[dict[str, Any]] = []
        self._selected_index = 0

    @classmethod
    def load(cls, data_path: Path | None = None) -> "QuestEditorModel":
        model = cls(data_path)
        model.reload()
        return model

    def reload(self) -> None:
        payload = json.loads(self._data_path.read_text(encoding="utf-8"))
        raw_quests = payload.get("quests") if isinstance(payload, dict) else None
        if isinstance(raw_quests, list):
            quests = [dict(quest) for quest in raw_quests if isinstance(quest, dict)]
        else:
            quests = []
        self._quests = quests
        self._selected_index = self._clamp_index(self._selected_index)

    def quests(self) -> list[dict[str, Any]]:
        return [dict(quest) for quest in self._quests]

    @property
    def quest_count(self) -> int:
        return len(self._quests)

    def selected_index(self) -> int:
        self._selected_index = self._clamp_index(self._selected_index)
        return self._selected_index

    def set_selected_index(self, index: int) -> bool:
        next_index = self._clamp_index(index)
        changed = next_index != self._selected_index
        self._selected_index = next_index
        return changed

    def selected_quest(self) -> dict[str, Any] | None:
        if not self._quests:
            self._selected_index = 0
            return None
        return dict(self._quests[self.selected_index()])

    def list_rows(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for quest in self._quests:
            quest_id = _string_value(quest.get("id"))
            title = _string_value(quest.get("title")) or quest_id
            rows.append((title, quest_id))
        return rows

    def scalar_detail_rows(self) -> list[tuple[str, str, str]]:
        quest = self.selected_quest()
        if quest is None:
            return []
        rows: list[tuple[str, str, str]] = []
        for field_path in QUEST_SCALAR_FIELD_ORDER:
            value = quest.get(field_path)
            if value is None or value == "":
                continue
            rows.append((_label_for_field(field_path), _format_value(value), field_path))
        return rows

    def complex_detail_rows(self) -> list[tuple[str, str]]:
        quest = self.selected_quest()
        if quest is None:
            return []
        rows: list[tuple[str, str]] = []
        for field_path in QUEST_COMPLEX_FIELD_ORDER:
            value = quest.get(field_path)
            if _is_empty_complex_value(value):
                continue
            rows.append((_label_for_field(field_path), _format_value(value)))
        return rows

    def _clamp_index(self, index: int) -> int:
        if not self._quests:
            return 0
        return max(0, min(int(index), len(self._quests) - 1))


def stage_rows(quest: dict[str, Any]) -> list[tuple[str, str]]:
    stages = quest.get("stages")
    if not isinstance(stages, list):
        return []
    rows: list[tuple[str, str]] = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        stage_id = _string_value(stage.get("id")) or f"stage_{index}"
        summary = _string_value(stage.get("title")) or _string_value(stage.get("text")) or "(untitled)"
        rows.append((stage_id, summary))
    return rows


def _label_for_field(field_path: str) -> str:
    return {
        "id": "ID",
        "title": "Title",
        "description": "Description",
        "type": "Type",
        "start_toast": "Start toast",
        "complete_toast": "Complete toast",
        "stages": "Stages",
        "steps": "Steps",
        "reward": "Reward",
        "requires_flags": "Requires flags",
        "blocks_flags": "Blocks flags",
    }.get(field_path, field_path)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return ", ".join(str(item) for item in value)
    try:
        text = _format_structured_value(value, sort_keys=True, separators=(",", ":"))
    except TypeError:
        text = repr(value)
    return text if len(text) <= 96 else f"{text[:93]}..."


def _string_value(value: Any) -> str:
    return str(value or "").strip()


def _is_empty_complex_value(value: Any) -> bool:
    return value is None or value == [] or value == {}


def validate_quest_entries(entries: list[dict[str, Any]], target_path: str | Path) -> list[str]:
    """Return validation error messages for editable quest payloads."""
    from engine.quest_runtime.validation import validate_quest_file  # noqa: PLC0415

    errors = validate_quest_file(Path(target_path), {"quests": entries})
    return [error.message for error in errors]


def save_quests(entries: list[dict[str, Any]], target_path: str | Path) -> None:
    """Persist quest dictionaries to assets/data/quests.json shape."""
    from engine.persistence_io import write_json_atomic  # noqa: PLC0415

    errors = validate_quest_entries(entries, target_path)
    if errors:
        raise ValueError("; ".join(errors))
    write_json_atomic(Path(target_path), {"quests": entries}, sort_keys=False, trailing_newline=True)
