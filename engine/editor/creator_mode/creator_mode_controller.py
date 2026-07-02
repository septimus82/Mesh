"""Controller for the read-only Creator Mode shell."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .creator_door_panel import build_creator_door_panel
from .creator_door_selection import build_creator_door_request_from_selection
from .creator_door_workflow import build_creator_door_workflow
from .creator_inspector import build_creator_inspector
from .creator_state import CreatorModeSnapshot


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
        inspector = build_creator_inspector(selected)
        door_panel = self._door_panel(selected)
        return CreatorModeSnapshot(
            active=self._active,
            selected_kind=inspector.kind,
            selected_title=inspector.title,
            selected_summary=inspector.summary,
            inspector=inspector,
            door_panel=door_panel,
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

    def _door_panel(self, selected: Mapping[str, Any] | None) -> Any:
        request = build_creator_door_request_from_selection(
            selected,
            source_scene=self._current_scene_path(),
        )
        if request is None:
            return None
        workflow = build_creator_door_workflow(request)
        return build_creator_door_panel(workflow, self._proposal_bridge())

    def _current_scene_path(self) -> str:
        scene_controller = getattr(getattr(self._editor, "window", None), "scene_controller", None)
        return str(getattr(scene_controller, "current_scene_path", "") or "")

    def _proposal_bridge(self) -> object:
        return getattr(self._editor, "live_bridge", None)
