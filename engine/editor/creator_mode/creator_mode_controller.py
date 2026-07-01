"""Controller for the read-only Creator Mode shell."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .creator_state import CreatorModeSnapshot
from .creator_terms import classify_entity_snapshot, selected_title, summarize_entity_snapshot


class CreatorModeController:
    """Owns Creator Mode visibility and read-only UI snapshots."""

    def __init__(self, editor: Any | None = None) -> None:
        self._editor = editor
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def toggle(self) -> bool:
        self._active = not self._active
        return self._active

    def show(self) -> None:
        self._active = True

    def hide(self) -> None:
        self._active = False

    def build_snapshot(self) -> CreatorModeSnapshot:
        selected = self._selected_entity_snapshot()
        return CreatorModeSnapshot(
            active=self._active,
            selected_kind=classify_entity_snapshot(selected),
            selected_title=selected_title(selected),
            selected_summary=summarize_entity_snapshot(selected),
        )

    def _selected_entity_snapshot(self) -> Mapping[str, Any] | None:
        editor = self._editor
        if editor is None:
            return None

        selected = getattr(editor, "selected_entity", None)
        data = getattr(selected, "mesh_entity_data", None)
        if isinstance(data, Mapping):
            return data

        if isinstance(selected, Mapping):
            return selected

        getter = getattr(editor, "_get_selected_entity_json_for_inspector", None)
        if callable(getter):
            value = getter()
            if isinstance(value, Mapping):
                return value

        return None
