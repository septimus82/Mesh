"""Controller for the read-only Creator Mode shell."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .creator_door_panel import build_creator_door_panel
from .creator_door_selection import build_creator_door_request_from_selection
from .creator_door_staging import CreatorDoorStagingResult, stage_creator_door_proposal
from .creator_door_workflow import build_creator_door_workflow
from .creator_inspector import build_creator_inspector
from .creator_state import CreatorModeSnapshot

_DOOR_STAGE_PROPOSAL_ACTION = "door.stage_proposal"


class CreatorModeController:
    """Owns Creator Mode visibility and read-only UI snapshots."""

    def __init__(self, editor: Any | None = None) -> None:
        self._editor = editor
        self._active = False
        self._last_action_message = ""
        self._last_action_ok: bool | None = None

    @property
    def last_action_message(self) -> str:
        return self._last_action_message

    @property
    def last_action_ok(self) -> bool | None:
        return self._last_action_ok

    @property
    def active(self) -> bool:
        return self._active

    def toggle(self) -> bool:
        self._active = not self._active
        if not self._active:
            self._clear_last_action_state()
        return self._active

    def show(self) -> None:
        self._active = True

    def hide(self) -> None:
        self._active = False
        self._clear_last_action_state()

    def stage_selected_door_proposal(self) -> CreatorDoorStagingResult:
        """Stage a door proposal for the currently selected door entity."""

        selected = self._selected_entity_snapshot()
        request = build_creator_door_request_from_selection(
            selected,
            source_scene=self._current_scene_path(),
        )
        if request is None:
            return CreatorDoorStagingResult(
                ok=False,
                errors=("No stageable door is selected.",),
            )

        workflow = build_creator_door_workflow(request)
        return stage_creator_door_proposal(workflow, self._proposal_bridge())

    def handle_overlay_click(self, x: float, y: float) -> CreatorDoorStagingResult | None:
        """Handle a Creator Mode overlay click when it hits an enabled action."""

        if not self._active:
            return None

        editor = self._editor
        if editor is None:
            return None

        from .creator_overlay_click import resolve_creator_overlay_click_action  # noqa: PLC0415

        action_id = resolve_creator_overlay_click_action(self, x, y)
        if action_id != _DOOR_STAGE_PROPOSAL_ACTION:
            return None

        result = self.stage_selected_door_proposal()
        self._store_staging_result(result)
        return result

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
            last_action_message=self._last_action_message,
            last_action_ok=self._last_action_ok,
        )

    def _clear_last_action_state(self) -> None:
        self._last_action_message = ""
        self._last_action_ok = None

    def _store_staging_result(self, result: CreatorDoorStagingResult) -> None:
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._last_action_message = f"Door proposal staged: {proposal_id}"
            else:
                self._last_action_message = "Door proposal staged."
            self._last_action_ok = True
            return

        message = result.errors[0] if result.errors else "Failed to stage door proposal."
        self._last_action_message = str(message)
        self._last_action_ok = False

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
