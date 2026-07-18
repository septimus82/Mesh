"""Controller for the read-only Creator Mode shell."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_door_panel import (
    CreatorDoorPanelAction,
    CreatorDoorPanelModel,
    build_creator_door_panel,
)
from .creator_door_selection import build_creator_door_request_from_selection
from .creator_door_staging import CreatorDoorStagingResult, stage_creator_door_proposal
from .creator_door_workflow import CreatorDoorWorkflowRequest, build_creator_door_workflow
from .creator_entity_duplicate_panel import (
    ENTITY_DUPLICATE_STAGE_ACTION_ID,
    CreatorEntityDuplicatePanelModel,
    build_creator_entity_duplicate_panel,
    request_for_duplicate_panel,
)
from .creator_entity_duplicate_request import creator_entity_duplicate_request_key
from .creator_entity_duplicate_staging import (
    CreatorEntityDuplicateStagingResult,
    stage_creator_entity_duplicate_proposal,
)
from .creator_entity_move_actions import ENTITY_MOVE_ACTION_ID_SET
from .creator_entity_move_panel import (
    CreatorEntityMovePanelModel,
    build_creator_entity_move_panel,
    request_for_panel_action,
)
from .creator_entity_move_request import creator_entity_move_request_key
from .creator_entity_move_staging import (
    CreatorEntityMoveStagingResult,
    stage_creator_entity_move_proposal,
)
from .creator_entity_opacity_panel import (
    ENTITY_OPACITY_DRAFT_ACTION_ID,
    ENTITY_OPACITY_PRESET_ACTION_PREFIX,
    ENTITY_OPACITY_STAGE_ACTION_ID,
    CreatorEntityOpacityPanelModel,
    build_creator_entity_opacity_panel,
    preset_percent_for_action,
    request_for_opacity_panel,
)
from .creator_entity_opacity_request import (
    alpha_to_draft_percent,
    creator_entity_opacity_request_key,
    resolve_alpha_state,
)
from .creator_entity_opacity_staging import (
    CreatorEntityOpacityStagingResult,
    stage_creator_entity_opacity_proposal,
)
from .creator_entity_rename_panel import (
    ENTITY_RENAME_DRAFT_ACTION_ID,
    ENTITY_RENAME_STAGE_ACTION_ID,
    CreatorEntityRenamePanelModel,
    build_creator_entity_rename_panel,
    request_for_rename_panel,
)
from .creator_entity_rename_request import (
    creator_entity_rename_request_key,
)
from .creator_entity_rename_staging import (
    CreatorEntityRenameStagingResult,
    stage_creator_entity_rename_proposal,
)
from .creator_inspector import build_creator_inspector
from .creator_proposal_accept_readiness import build_creator_proposal_accept_readiness_from_status
from .creator_proposal_handoff import PROPOSAL_OPEN_INBOX_ACTION_ID, build_creator_proposal_handoff
from .creator_proposal_review_details import build_creator_proposal_review_details_from_status
from .creator_proposal_status import build_creator_proposal_status
from .creator_state import CreatorModeSnapshot

_DOOR_STAGE_PROPOSAL_ACTION = "door.stage_proposal"
_AI_PROPOSALS_TAB = "AI Proposals"


@dataclass(frozen=True, slots=True)
class CreatorProposalInboxNavigationResult:
    """Result for Creator Mode to AI Proposals dock navigation."""

    ok: bool
    reason: str = ""
    pending_count: int = 0


class CreatorModeController:
    """Owns Creator Mode visibility and read-only UI snapshots."""

    def __init__(self, editor: Any | None = None) -> None:
        self._editor = editor
        self._active = False
        self._last_action_message = ""
        self._last_action_ok: bool | None = None
        self._last_staged_door_key = ""
        self._last_staged_proposal_id = ""
        self._staged_move_keys: dict[str, str] = {}
        self._staged_rename_keys: dict[str, str] = {}
        self._staged_opacity_keys: dict[str, str] = {}
        self._staged_duplicate_keys: dict[str, str] = {}
        self._rename_draft = ""
        self._rename_selection_key = ""
        self._rename_text_focused = False
        self._opacity_draft = ""
        self._opacity_selection_key = ""
        self._opacity_text_focused = False

    @property
    def last_action_message(self) -> str:
        return self._last_action_message

    @property
    def last_action_ok(self) -> bool | None:
        return self._last_action_ok

    @property
    def active(self) -> bool:
        return self._active

    @property
    def rename_text_focused(self) -> bool:
        return bool(self._rename_text_focused)

    @property
    def opacity_text_focused(self) -> bool:
        return bool(self._opacity_text_focused)

    def toggle(self) -> bool:
        self._active = not self._active
        if not self._active:
            self._clear_last_action_state()
            self._rename_text_focused = False
            self._opacity_text_focused = False
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

        request_key = self._door_request_key(request)
        if request_key == self._last_staged_door_key and self._last_staged_proposal_id:
            duplicate = CreatorDoorStagingResult(
                ok=False,
                errors=(f"Door proposal already staged: {self._last_staged_proposal_id}",),
            )
            self._store_staging_result(duplicate)
            return duplicate

        workflow = build_creator_door_workflow(request)
        result = stage_creator_door_proposal(workflow, self._proposal_bridge())
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._last_staged_door_key = request_key
                self._last_staged_proposal_id = proposal_id
        return result

    def handle_overlay_click(
        self,
        x: float,
        y: float,
    ) -> (
        CreatorDoorStagingResult
        | CreatorEntityMoveStagingResult
        | CreatorEntityDuplicateStagingResult
        | CreatorEntityOpacityStagingResult
        | CreatorEntityRenameStagingResult
        | CreatorProposalInboxNavigationResult
        | None
    ):
        """Handle a Creator Mode overlay click when it hits an enabled action."""

        if not self._active:
            return None

        editor = self._editor
        if editor is None:
            return None

        from .creator_overlay_click import resolve_creator_overlay_click_action  # noqa: PLC0415

        action_id = resolve_creator_overlay_click_action(self, x, y)
        if action_id != ENTITY_RENAME_DRAFT_ACTION_ID:
            self._rename_text_focused = False
        if action_id != ENTITY_OPACITY_DRAFT_ACTION_ID:
            self._opacity_text_focused = False
        if action_id == PROPOSAL_OPEN_INBOX_ACTION_ID:
            return self.open_ai_proposals_inbox()
        if action_id == ENTITY_RENAME_DRAFT_ACTION_ID:
            self._focus_rename_draft()
            return CreatorEntityRenameStagingResult(ok=False, errors=())
        if action_id == ENTITY_OPACITY_DRAFT_ACTION_ID:
            self._focus_opacity_draft()
            return CreatorEntityOpacityStagingResult(ok=False, errors=())
        if str(action_id or "").startswith(ENTITY_OPACITY_PRESET_ACTION_PREFIX):
            percent = preset_percent_for_action(str(action_id or ""))
            if not percent:
                return None
            self._sync_opacity_draft_for_selection(self._selected_entity_snapshot())
            self._opacity_draft = percent
            return CreatorEntityOpacityStagingResult(ok=False, errors=())
        if action_id == ENTITY_RENAME_STAGE_ACTION_ID:
            result = self.stage_selected_entity_rename()
            self._store_rename_staging_result(result)
            return result
        if action_id == ENTITY_OPACITY_STAGE_ACTION_ID:
            result = self.stage_selected_entity_opacity()
            self._store_opacity_staging_result(result)
            return result
        if action_id == ENTITY_DUPLICATE_STAGE_ACTION_ID:
            result = self.stage_selected_entity_duplicate()
            self._store_duplicate_staging_result(result)
            return result
        if action_id in ENTITY_MOVE_ACTION_ID_SET:
            result = self.stage_selected_entity_move(action_id)
            self._store_move_staging_result(result)
            return result
        if action_id != _DOOR_STAGE_PROPOSAL_ACTION:
            return None

        result = self.stage_selected_door_proposal()
        self._store_staging_result(result)
        return result

    def stage_selected_entity_duplicate(self) -> CreatorEntityDuplicateStagingResult:
        """Stage an authored-entity duplicate proposal for the current selection."""

        selected = self._selected_entity_snapshot()
        request = request_for_duplicate_panel(
            selected,
            source_scene=self._current_scene_path(),
            authored_scene=self._authored_scene_payload(),
            duplicate_offset=self._duplicate_offset(),
        )
        if not request.ok:
            return CreatorEntityDuplicateStagingResult(
                ok=False,
                errors=(request.reason or "Duplicate is unavailable.",),
            )

        request_key = creator_entity_duplicate_request_key(request)
        staged_id = str(self._staged_duplicate_keys.get(request_key) or "").strip()
        if staged_id and self._proposal_still_pending(staged_id):
            return CreatorEntityDuplicateStagingResult(
                ok=False,
                errors=(f"Duplicate proposal already staged: {staged_id}",),
            )
        if staged_id:
            self._staged_duplicate_keys.pop(request_key, None)

        result = stage_creator_entity_duplicate_proposal(request, self._proposal_bridge())
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._staged_duplicate_keys[request_key] = proposal_id
        return result

    def stage_selected_entity_move(self, action_id: str) -> CreatorEntityMoveStagingResult:
        """Stage a one-grid-step movement proposal for the current selection."""

        selected = self._selected_entity_snapshot()
        request = request_for_panel_action(
            selected,
            action_id=action_id,
            source_scene=self._current_scene_path(),
            grid_step=self._editor_grid_step(),
        )
        if not request.ok:
            return CreatorEntityMoveStagingResult(
                ok=False,
                errors=(request.reason or "Movement is unavailable.",),
            )

        request_key = creator_entity_move_request_key(request)
        staged_id = str(self._staged_move_keys.get(request_key) or "").strip()
        if staged_id and self._proposal_still_pending(staged_id):
            return CreatorEntityMoveStagingResult(
                ok=False,
                errors=(f"Movement proposal already staged: {staged_id}",),
            )
        if staged_id:
            self._staged_move_keys.pop(request_key, None)

        result = stage_creator_entity_move_proposal(request, self._proposal_bridge())
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._staged_move_keys[request_key] = proposal_id
        return result

    def stage_selected_entity_rename(self) -> CreatorEntityRenameStagingResult:
        """Stage a display-label rename proposal for the current selection."""

        selected = self._selected_entity_snapshot()
        self._sync_rename_draft_for_selection(selected)
        request = request_for_rename_panel(
            selected,
            source_scene=self._current_scene_path(),
            draft_label=self._rename_draft,
        )
        if not request.ok:
            return CreatorEntityRenameStagingResult(
                ok=False,
                errors=(request.reason or "Rename is unavailable.",),
            )

        request_key = creator_entity_rename_request_key(request)
        staged_id = str(self._staged_rename_keys.get(request_key) or "").strip()
        if staged_id and self._proposal_still_pending(staged_id):
            return CreatorEntityRenameStagingResult(
                ok=False,
                errors=(f"Rename proposal already staged: {staged_id}",),
            )
        if staged_id:
            self._staged_rename_keys.pop(request_key, None)

        result = stage_creator_entity_rename_proposal(request, self._proposal_bridge())
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._staged_rename_keys[request_key] = proposal_id
        return result

    def stage_selected_entity_opacity(self) -> CreatorEntityOpacityStagingResult:
        """Stage an authored alpha/opacity proposal for the current selection."""

        selected = self._selected_entity_snapshot()
        self._sync_opacity_draft_for_selection(selected)
        request = request_for_opacity_panel(
            selected,
            source_scene=self._current_scene_path(),
            draft_percent=self._opacity_draft,
        )
        if not request.ok:
            return CreatorEntityOpacityStagingResult(
                ok=False,
                errors=(request.reason or "Opacity is unavailable.",),
            )

        request_key = creator_entity_opacity_request_key(request)
        staged_id = str(self._staged_opacity_keys.get(request_key) or "").strip()
        if staged_id and self._proposal_still_pending(staged_id):
            return CreatorEntityOpacityStagingResult(
                ok=False,
                errors=(f"Opacity proposal already staged: {staged_id}",),
            )
        if staged_id:
            self._staged_opacity_keys.pop(request_key, None)

        result = stage_creator_entity_opacity_proposal(request, self._proposal_bridge())
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._staged_opacity_keys[request_key] = proposal_id
                self._opacity_text_focused = False
        return result

    def handle_key_input(self, key: int, modifiers: int = 0) -> bool:
        """Handle typing while a Creator text field is focused."""

        if not self._active or not (self._rename_text_focused or self._opacity_text_focused):
            return False
        import engine.optional_arcade as optional_arcade  # noqa: PLC0415

        arcade_key = optional_arcade.arcade.key
        if key == arcade_key.ESCAPE:
            self._rename_text_focused = False
            self._opacity_text_focused = False
            return True
        if key == arcade_key.BACKSPACE:
            if self._opacity_text_focused:
                self._opacity_draft = self._opacity_draft[:-1]
            else:
                self._rename_draft = self._rename_draft[:-1]
            return True
        if key == getattr(arcade_key, "DELETE", -1):
            if self._opacity_text_focused:
                self._opacity_draft = ""
            return True
        if key in (arcade_key.ENTER, arcade_key.RETURN):
            return True
        if modifiers & (getattr(arcade_key, "MOD_CTRL", 0) | getattr(arcade_key, "MOD_ALT", 0)):
            return True
        if 32 <= int(key) <= 0x10FFFF:
            text = chr(int(key))
            if text.isprintable():
                if self._opacity_text_focused:
                    self._opacity_draft += text
                else:
                    self._rename_draft += text
                return True
        return True

    def open_ai_proposals_inbox(self) -> CreatorProposalInboxNavigationResult:
        """Leave Creator Mode and show the official AI Proposals dock tab."""

        if not self._active:
            return CreatorProposalInboxNavigationResult(ok=False, reason="creator_inactive")

        editor = self._editor
        if editor is None:
            return CreatorProposalInboxNavigationResult(ok=False, reason="missing_editor")

        inbox = getattr(editor, "proposal_inbox", None)
        if inbox is None:
            return CreatorProposalInboxNavigationResult(ok=False, reason="missing_proposal_inbox")

        dock = getattr(editor, "dock", None)
        get_collapsed = getattr(dock, "get_right_collapsed", None)
        toggle_right_dock = getattr(dock, "toggle_right_dock", None)
        apply_tab_change = getattr(dock, "apply_tab_change", None)
        get_maximized = getattr(dock, "get_viewport_maximized", None)
        toggle_maximized = getattr(dock, "toggle_viewport_maximized", None)
        if (
            dock is None
            or not callable(get_collapsed)
            or not callable(toggle_right_dock)
            or not callable(apply_tab_change)
            or not callable(get_maximized)
            or not callable(toggle_maximized)
        ):
            return CreatorProposalInboxNavigationResult(ok=False, reason="missing_dock_controller")

        pending = self._pending_proposals()
        pending_count = len(pending)
        if pending_count <= 0:
            return CreatorProposalInboxNavigationResult(ok=False, reason="no_pending_proposals")

        original_tab = str(getattr(dock, "right_tab", "") or "")
        original_collapsed = bool(get_collapsed())
        original_maximized = bool(get_maximized())
        viewport_restored = False
        tab_changed = False
        collapsed_changed = False

        if original_maximized:
            toggle_maximized(editor)
            viewport_restored = True
            if bool(get_maximized()):
                self._restore_dock_navigation_state(
                    dock=dock,
                    original_tab=original_tab,
                    original_collapsed=original_collapsed,
                    original_maximized=original_maximized,
                    viewport_restored=viewport_restored,
                    tab_changed=tab_changed,
                    collapsed_changed=collapsed_changed,
                    editor=editor,
                )
                return CreatorProposalInboxNavigationResult(
                    ok=False,
                    reason="viewport_restore_failed",
                    pending_count=pending_count,
                )

        if bool(get_collapsed()):
            toggle_right_dock(editor)
            collapsed_changed = True
            if bool(get_collapsed()):
                self._restore_dock_navigation_state(
                    dock=dock,
                    original_tab=original_tab,
                    original_collapsed=original_collapsed,
                    original_maximized=original_maximized,
                    viewport_restored=viewport_restored,
                    tab_changed=tab_changed,
                    collapsed_changed=collapsed_changed,
                    editor=editor,
                )
                return CreatorProposalInboxNavigationResult(
                    ok=False,
                    reason="right_dock_expand_failed",
                    pending_count=pending_count,
                )

        current_tab = str(getattr(dock, "right_tab", "") or "")
        if current_tab != _AI_PROPOSALS_TAB:
            if not bool(apply_tab_change(editor, "right", _AI_PROPOSALS_TAB)):
                self._restore_dock_navigation_state(
                    dock=dock,
                    original_tab=original_tab,
                    original_collapsed=original_collapsed,
                    original_maximized=original_maximized,
                    viewport_restored=viewport_restored,
                    tab_changed=tab_changed,
                    collapsed_changed=collapsed_changed,
                    editor=editor,
                )
                return CreatorProposalInboxNavigationResult(
                    ok=False,
                    reason="ai_proposals_tab_unavailable",
                    pending_count=pending_count,
                )
            tab_changed = True

        if (
            bool(get_maximized())
            or bool(get_collapsed())
            or str(getattr(dock, "right_tab", "") or "") != _AI_PROPOSALS_TAB
        ):
            self._restore_dock_navigation_state(
                dock=dock,
                original_tab=original_tab,
                original_collapsed=original_collapsed,
                original_maximized=original_maximized,
                viewport_restored=viewport_restored,
                tab_changed=tab_changed,
                collapsed_changed=collapsed_changed,
                editor=editor,
            )
            return CreatorProposalInboxNavigationResult(
                ok=False,
                reason="ai_proposals_dock_not_visible",
                pending_count=pending_count,
            )

        self.hide()
        return CreatorProposalInboxNavigationResult(ok=True, pending_count=pending_count)

    def build_snapshot(self) -> CreatorModeSnapshot:
        selected = self._selected_entity_snapshot()
        self._sync_rename_draft_for_selection(selected)
        self._sync_opacity_draft_for_selection(selected)
        inspector = build_creator_inspector(selected)
        self._prune_stale_move_keys()
        self._prune_stale_rename_keys()
        self._prune_stale_opacity_keys()
        self._prune_stale_duplicate_keys()
        movement_panel = self._movement_panel(selected)
        rename_panel = self._rename_panel(selected)
        opacity_panel = self._opacity_panel(selected)
        duplicate_panel = self._duplicate_panel(selected)
        door_panel = self._door_panel(selected)
        proposal_status = build_creator_proposal_status(self._proposal_bridge())
        return CreatorModeSnapshot(
            active=self._active,
            selected_kind=inspector.kind,
            selected_title=inspector.title,
            selected_summary=inspector.summary,
            inspector=inspector,
            movement_panel=movement_panel,
            rename_panel=rename_panel,
            opacity_panel=opacity_panel,
            duplicate_panel=duplicate_panel,
            door_panel=door_panel,
            proposal_status=proposal_status,
            proposal_accept_readiness=build_creator_proposal_accept_readiness_from_status(
                proposal_status,
            ),
            proposal_review_details=build_creator_proposal_review_details_from_status(
                proposal_status,
            ),
            proposal_handoff=build_creator_proposal_handoff(self._editor, proposal_status),
            last_action_message=self._last_action_message,
            last_action_ok=self._last_action_ok,
        )

    def _clear_last_action_state(self) -> None:
        self._last_action_message = ""
        self._last_action_ok = None
        self._last_staged_door_key = ""
        self._last_staged_proposal_id = ""
        self._staged_move_keys.clear()
        self._staged_rename_keys.clear()
        self._staged_opacity_keys.clear()
        self._staged_duplicate_keys.clear()
        self._rename_draft = ""
        self._rename_selection_key = ""
        self._rename_text_focused = False
        self._opacity_draft = ""
        self._opacity_selection_key = ""
        self._opacity_text_focused = False

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

    def _store_duplicate_staging_result(
        self,
        result: CreatorEntityDuplicateStagingResult,
    ) -> None:
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._last_action_message = f"Duplicate proposal staged: {proposal_id}"
            else:
                self._last_action_message = "Duplicate proposal staged."
            self._last_action_ok = True
            return

        message = result.errors[0] if result.errors else "Failed to stage duplicate proposal."
        self._last_action_message = str(message)
        self._last_action_ok = False

    def _store_opacity_staging_result(self, result: CreatorEntityOpacityStagingResult) -> None:
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._last_action_message = f"Opacity proposal staged: {proposal_id}"
            else:
                self._last_action_message = "Opacity proposal staged."
            self._last_action_ok = True
            self._opacity_text_focused = False
            return

        message = result.errors[0] if result.errors else "Failed to stage opacity proposal."
        self._last_action_message = str(message)
        self._last_action_ok = False

    def _store_move_staging_result(self, result: CreatorEntityMoveStagingResult) -> None:
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._last_action_message = f"Movement proposal staged: {proposal_id}"
            else:
                self._last_action_message = "Movement proposal staged."
            self._last_action_ok = True
            return

        message = result.errors[0] if result.errors else "Failed to stage movement proposal."
        self._last_action_message = str(message)
        self._last_action_ok = False

    def _store_rename_staging_result(self, result: CreatorEntityRenameStagingResult) -> None:
        if result.ok:
            proposal_id = str(result.proposal_id or "").strip()
            if proposal_id:
                self._last_action_message = f"Rename proposal staged: {proposal_id}"
            else:
                self._last_action_message = "Rename proposal staged."
            self._last_action_ok = True
            self._rename_text_focused = False
            return

        message = result.errors[0] if result.errors else "Failed to stage rename proposal."
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

    def _movement_panel(
        self,
        selected: Mapping[str, Any] | None,
    ) -> CreatorEntityMovePanelModel:
        return build_creator_entity_move_panel(
            selected,
            source_scene=self._current_scene_path(),
            grid_step=self._editor_grid_step(),
            bridge=self._proposal_bridge(),
            duplicate_keys=dict(self._staged_move_keys),
        )

    def _rename_panel(
        self,
        selected: Mapping[str, Any] | None,
    ) -> CreatorEntityRenamePanelModel:
        return build_creator_entity_rename_panel(
            selected,
            source_scene=self._current_scene_path(),
            draft_label=self._rename_draft,
            bridge=self._proposal_bridge(),
            focused=self._rename_text_focused,
            duplicate_keys=dict(self._staged_rename_keys),
        )

    def _opacity_panel(
        self,
        selected: Mapping[str, Any] | None,
    ) -> CreatorEntityOpacityPanelModel:
        return build_creator_entity_opacity_panel(
            selected,
            source_scene=self._current_scene_path(),
            draft_percent=self._opacity_draft,
            bridge=self._proposal_bridge(),
            focused=self._opacity_text_focused,
            duplicate_keys=dict(self._staged_opacity_keys),
        )

    def _duplicate_panel(
        self,
        selected: Mapping[str, Any] | None,
    ) -> CreatorEntityDuplicatePanelModel:
        return build_creator_entity_duplicate_panel(
            selected,
            source_scene=self._current_scene_path(),
            authored_scene=self._authored_scene_payload(),
            duplicate_offset=self._duplicate_offset(),
            bridge=self._proposal_bridge(),
            duplicate_keys=dict(self._staged_duplicate_keys),
        )

    def _door_panel(self, selected: Mapping[str, Any] | None) -> Any:
        request = build_creator_door_request_from_selection(
            selected,
            source_scene=self._current_scene_path(),
        )
        if request is None:
            return None
        workflow = build_creator_door_workflow(request)
        panel = build_creator_door_panel(workflow, self._proposal_bridge())
        return self._apply_duplicate_stage_guard_to_panel(panel, request)

    def _editor_grid_step(self) -> float:
        editor = self._editor
        if editor is None:
            return 0.0
        try:
            return float(getattr(editor, "grid_size", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _proposal_still_pending(self, proposal_id: str) -> bool:
        target = str(proposal_id or "").strip()
        if not target:
            return False
        for item in self._pending_proposals():
            if isinstance(item, Mapping):
                item_id = str(item.get("proposal_id") or item.get("id") or "").strip()
            else:
                item_id = str(
                    getattr(item, "proposal_id", None) or getattr(item, "id", None) or ""
                ).strip()
            if item_id == target:
                return True
        return False

    def _prune_stale_move_keys(self) -> None:
        if not self._staged_move_keys:
            return
        pending_ids: set[str] = set()
        for item in self._pending_proposals():
            if isinstance(item, Mapping):
                item_id = str(item.get("proposal_id") or item.get("id") or "").strip()
            else:
                item_id = str(
                    getattr(item, "proposal_id", None) or getattr(item, "id", None) or ""
                ).strip()
            if item_id:
                pending_ids.add(item_id)
        stale = [
            key
            for key, proposal_id in self._staged_move_keys.items()
            if proposal_id not in pending_ids
        ]
        for key in stale:
            self._staged_move_keys.pop(key, None)

    def _prune_stale_rename_keys(self) -> None:
        if not self._staged_rename_keys:
            return
        pending_ids = self._pending_proposal_ids()
        stale = [
            key
            for key, proposal_id in self._staged_rename_keys.items()
            if proposal_id not in pending_ids
        ]
        for key in stale:
            self._staged_rename_keys.pop(key, None)

    def _prune_stale_opacity_keys(self) -> None:
        if not self._staged_opacity_keys:
            return
        pending_ids = self._pending_proposal_ids()
        stale = [
            key
            for key, proposal_id in self._staged_opacity_keys.items()
            if proposal_id not in pending_ids
        ]
        for key in stale:
            self._staged_opacity_keys.pop(key, None)

    def _prune_stale_duplicate_keys(self) -> None:
        if not self._staged_duplicate_keys:
            return
        pending_ids = self._pending_proposal_ids()
        stale = [
            key
            for key, proposal_id in self._staged_duplicate_keys.items()
            if proposal_id not in pending_ids
        ]
        for key in stale:
            self._staged_duplicate_keys.pop(key, None)

    def _pending_proposal_ids(self) -> set[str]:
        pending_ids: set[str] = set()
        for item in self._pending_proposals():
            if isinstance(item, Mapping):
                item_id = str(item.get("proposal_id") or item.get("id") or "").strip()
            else:
                item_id = str(
                    getattr(item, "proposal_id", None) or getattr(item, "id", None) or ""
                ).strip()
            if item_id:
                pending_ids.add(item_id)
        return pending_ids

    def _focus_rename_draft(self) -> None:
        selected = self._selected_entity_snapshot()
        self._sync_rename_draft_for_selection(selected)
        self._rename_text_focused = bool(self._rename_selection_key)

    def _focus_opacity_draft(self) -> None:
        selected = self._selected_entity_snapshot()
        self._sync_opacity_draft_for_selection(selected)
        self._opacity_text_focused = bool(self._opacity_selection_key)

    def _sync_rename_draft_for_selection(self, selected: Mapping[str, Any] | None) -> None:
        key = self._rename_key_for_selection(selected)
        if key == self._rename_selection_key:
            return
        self._rename_selection_key = key
        self._rename_text_focused = False
        if isinstance(selected, Mapping):
            label = selected.get("name")
            self._rename_draft = label if isinstance(label, str) else ""
        else:
            self._rename_draft = ""

    def _sync_opacity_draft_for_selection(self, selected: Mapping[str, Any] | None) -> None:
        key = self._opacity_key_for_selection(selected)
        if key == self._opacity_selection_key:
            return
        self._opacity_selection_key = key
        self._opacity_text_focused = False
        if isinstance(selected, Mapping):
            alpha_state = resolve_alpha_state(selected)
            self._opacity_draft = (
                alpha_to_draft_percent(alpha_state.effective_value)
                if alpha_state is not None
                else ""
            )
        else:
            self._opacity_draft = ""

    def _rename_key_for_selection(self, selected: Mapping[str, Any] | None) -> str:
        if not isinstance(selected, Mapping):
            return ""
        for key in ("id", "entity_id"):
            value = selected.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _opacity_key_for_selection(self, selected: Mapping[str, Any] | None) -> str:
        return self._rename_key_for_selection(selected)

    def _door_request_key(self, request: CreatorDoorWorkflowRequest) -> str:
        """Stable key for duplicate-stage detection."""

        return "|".join(
            (
                str(request.source_scene or ""),
                str(request.source_entity_id or ""),
                str(request.destination_scene or ""),
                str(request.destination_spawn_id or ""),
                str(request.trigger or ""),
                str(request.transition_behaviour or ""),
                str(request.scene_exit_listen_event or ""),
                str(request.interactable_event or ""),
                "1" if request.locked else "0",
                str(request.required_flag or ""),
                ",".join(request.entity_require_flags),
            )
        )

    def _apply_duplicate_stage_guard_to_panel(
        self,
        panel: CreatorDoorPanelModel,
        request: CreatorDoorWorkflowRequest,
    ) -> CreatorDoorPanelModel:
        if not self._last_staged_proposal_id:
            return panel
        if self._door_request_key(request) != self._last_staged_door_key:
            return panel

        reason = f"Already staged: {self._last_staged_proposal_id}"
        actions = tuple(
            CreatorDoorPanelAction(
                label=action.label,
                enabled=False,
                reason=reason,
            )
            if action.label == "Stage Proposal"
            else action
            for action in panel.actions
        )
        return CreatorDoorPanelModel(
            title=panel.title,
            status=panel.status,
            summary=panel.summary,
            sections=panel.sections,
            actions=actions,
        )

    def _current_scene_path(self) -> str:
        scene_controller = getattr(getattr(self._editor, "window", None), "scene_controller", None)
        return str(getattr(scene_controller, "current_scene_path", "") or "")

    def _authored_scene_payload(self) -> Mapping[str, Any] | None:
        scene_controller = getattr(getattr(self._editor, "window", None), "scene_controller", None)
        getter = getattr(scene_controller, "get_authored_scene_payload", None)
        if callable(getter):
            payload = getter()
            if isinstance(payload, Mapping):
                return payload
        for attr in ("_loaded_scene_source_data", "_loaded_scene_data"):
            payload = getattr(scene_controller, attr, None)
            if isinstance(payload, Mapping):
                return payload
        return None

    def _duplicate_offset(self) -> tuple[float, float]:
        try:
            from engine.entity_select_mode import get_duplicate_offset  # noqa: PLC0415

            dx, dy = get_duplicate_offset(getattr(self._editor, "window", None))
            return float(dx), float(dy)
        except (TypeError, ValueError, AttributeError):
            return 16.0, 16.0

    def _proposal_bridge(self) -> object:
        return getattr(self._editor, "live_bridge", None)

    def _pending_proposals(self) -> list[object]:
        bridge = self._proposal_bridge()
        list_pending = getattr(bridge, "list_pending_proposals", None)
        if not callable(list_pending):
            return []
        try:
            pending = list_pending()
        except Exception:  # noqa: BLE001  # REASON: navigation must fail closed if live bridge reads fail
            return []
        return pending if isinstance(pending, list) else []

    def _restore_dock_navigation_state(
        self,
        *,
        dock: object,
        original_tab: str,
        original_collapsed: bool,
        original_maximized: bool,
        viewport_restored: bool,
        tab_changed: bool,
        collapsed_changed: bool,
        editor: object,
    ) -> None:
        """Best-effort restore after a failed navigation attempt."""

        if tab_changed and original_tab:
            apply_tab_change = getattr(dock, "apply_tab_change", None)
            if callable(apply_tab_change):
                try:
                    apply_tab_change(editor, "right", original_tab)
                except Exception:  # noqa: BLE001  # REASON: best-effort rollback must not mask original failure
                    pass
        if collapsed_changed:
            get_collapsed = getattr(dock, "get_right_collapsed", None)
            toggle_right_dock = getattr(dock, "toggle_right_dock", None)
            if callable(get_collapsed) and callable(toggle_right_dock):
                try:
                    if bool(get_collapsed()) != original_collapsed:
                        toggle_right_dock(editor)
                except Exception:  # noqa: BLE001  # REASON: best-effort rollback must not mask original failure
                    pass
        if viewport_restored and original_maximized:
            get_maximized = getattr(dock, "get_viewport_maximized", None)
            toggle_maximized = getattr(dock, "toggle_viewport_maximized", None)
            if callable(get_maximized) and callable(toggle_maximized):
                try:
                    if not bool(get_maximized()):
                        toggle_maximized(editor)
                except Exception:  # noqa: BLE001  # REASON: best-effort rollback must not mask original failure
                    pass
