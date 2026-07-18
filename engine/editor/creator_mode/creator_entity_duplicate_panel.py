"""Creator Mode selected-entity duplicate panel model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_entity_duplicate_request import (
    CreatorEntityDuplicateRequest,
    build_creator_entity_duplicate_request,
    creator_entity_duplicate_request_key,
)

ENTITY_DUPLICATE_STAGE_ACTION_ID = "entity.duplicate.stage"


@dataclass(frozen=True, slots=True)
class CreatorEntityDuplicatePanelAction:
    """Duplicate action with enablement and hit-test identity."""

    label: str
    action_id: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorEntityDuplicatePanelModel:
    """Compact selected-entity duplicate section."""

    title: str
    available: bool
    source_entity_id: str
    duplicate_entity_id: str
    source_position_text: str
    duplicate_position_text: str
    offset_text: str
    reason: str
    action: CreatorEntityDuplicatePanelAction


def build_creator_entity_duplicate_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    authored_scene: Mapping[str, Any] | None,
    duplicate_offset: tuple[float, float],
    bridge: object | None,
    duplicate_keys: Mapping[str, str] | None = None,
) -> CreatorEntityDuplicatePanelModel:
    """Build duplicate panel state for the current selection."""

    request = build_creator_entity_duplicate_request(
        selected,
        source_scene=source_scene,
        authored_scene=authored_scene,
        duplicate_offset=duplicate_offset,
    )
    bridge_ok = callable(getattr(bridge, "stage_pending_proposal", None))
    action = CreatorEntityDuplicatePanelAction(
        label="Stage Duplicate Proposal",
        action_id=ENTITY_DUPLICATE_STAGE_ACTION_ID,
        enabled=False,
        reason=request.reason or "Duplicate proposals are unavailable for this entity type.",
    )
    if request.ok and not bridge_ok:
        action = CreatorEntityDuplicatePanelAction(
            label="Stage Duplicate Proposal",
            action_id=ENTITY_DUPLICATE_STAGE_ACTION_ID,
            enabled=False,
            reason="Proposal bridge is unavailable.",
        )
    elif request.ok:
        staged_id = ""
        request_key = creator_entity_duplicate_request_key(request)
        if isinstance(duplicate_keys, Mapping):
            staged_id = str(duplicate_keys.get(request_key) or "").strip()
        action = (
            CreatorEntityDuplicatePanelAction(
                label="Stage Duplicate Proposal",
                action_id=ENTITY_DUPLICATE_STAGE_ACTION_ID,
                enabled=False,
                reason=f"Already staged: {staged_id}",
            )
            if staged_id
            else CreatorEntityDuplicatePanelAction(
                label="Stage Duplicate Proposal",
                action_id=ENTITY_DUPLICATE_STAGE_ACTION_ID,
                enabled=True,
                reason="",
            )
        )
    return CreatorEntityDuplicatePanelModel(
        title="Duplicate",
        available=bool(request.ok and bridge_ok),
        source_entity_id=request.source_entity_id,
        duplicate_entity_id=request.duplicate_entity_id,
        source_position_text=f"({request.from_x:g}, {request.from_y:g})",
        duplicate_position_text=f"({request.to_x:g}, {request.to_y:g})",
        offset_text=f"Offset: {request.dx:g}, {request.dy:g}",
        reason=action.reason,
        action=action,
    )


def request_for_duplicate_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    authored_scene: Mapping[str, Any] | None,
    duplicate_offset: tuple[float, float],
) -> CreatorEntityDuplicateRequest:
    """Build the current duplicate request from controller state."""

    return build_creator_entity_duplicate_request(
        selected,
        source_scene=source_scene,
        authored_scene=authored_scene,
        duplicate_offset=duplicate_offset,
    )
