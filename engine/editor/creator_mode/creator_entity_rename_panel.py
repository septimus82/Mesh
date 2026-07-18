"""Creator Mode selected-entity display-label rename panel model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_entity_rename_request import (
    CreatorEntityRenameRequest,
    build_creator_entity_rename_request,
    normalize_display_label,
)

ENTITY_RENAME_STAGE_ACTION_ID = "entity.rename.stage"
ENTITY_RENAME_DRAFT_ACTION_ID = "entity.rename.draft"


@dataclass(frozen=True, slots=True)
class CreatorEntityRenamePanelAction:
    """One rename action with enablement and hit-test identity."""

    label: str
    action_id: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorEntityRenamePanelModel:
    """Compact selected-entity display-label rename section."""

    title: str
    available: bool
    entity_id: str
    current_label: str
    draft_label: str
    label_field: str
    focused: bool
    reason: str
    action: CreatorEntityRenamePanelAction


def build_creator_entity_rename_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    draft_label: str,
    bridge: object | None,
    focused: bool = False,
    duplicate_keys: Mapping[str, str] | None = None,
) -> CreatorEntityRenamePanelModel:
    """Build rename panel state for the current selection."""

    request = build_creator_entity_rename_request(
        selected,
        source_scene=source_scene,
        proposed_label=draft_label,
    )
    bridge_ok = callable(getattr(bridge, "stage_pending_proposal", None))
    current_label = request.current_label
    entity_id = request.entity_id
    if not current_label and isinstance(selected, Mapping):
        raw_label = selected.get("name")
        current_label = raw_label if isinstance(raw_label, str) else ""
    if not entity_id and isinstance(selected, Mapping):
        entity_id = _stable_entity_id(selected)

    action = CreatorEntityRenamePanelAction(
        label="Stage Rename Proposal",
        action_id=ENTITY_RENAME_STAGE_ACTION_ID,
        enabled=False,
        reason=request.reason or "Rename is unavailable.",
    )
    if not bridge_ok and entity_id:
        action = CreatorEntityRenamePanelAction(
            label="Stage Rename Proposal",
            action_id=ENTITY_RENAME_STAGE_ACTION_ID,
            enabled=False,
            reason="Proposal bridge is unavailable.",
        )
    elif request.ok:
        staged_id = ""
        from .creator_entity_rename_request import creator_entity_rename_request_key  # noqa: PLC0415

        request_key = creator_entity_rename_request_key(request)
        if isinstance(duplicate_keys, Mapping):
            staged_id = str(duplicate_keys.get(request_key) or "").strip()
        if staged_id:
            action = CreatorEntityRenamePanelAction(
                label="Stage Rename Proposal",
                action_id=ENTITY_RENAME_STAGE_ACTION_ID,
                enabled=False,
                reason=f"Already staged: {staged_id}",
            )
        else:
            action = CreatorEntityRenamePanelAction(
                label="Stage Rename Proposal",
                action_id=ENTITY_RENAME_STAGE_ACTION_ID,
                enabled=True,
                reason="",
            )

    return CreatorEntityRenamePanelModel(
        title="Rename",
        available=bool(request.ok and bridge_ok),
        entity_id=entity_id,
        current_label=current_label,
        draft_label=str(draft_label or ""),
        label_field=request.label_field,
        focused=bool(focused),
        reason=action.reason,
        action=action,
    )


def request_for_rename_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    draft_label: str,
) -> CreatorEntityRenameRequest:
    """Build the current rename request from the panel draft."""

    return build_creator_entity_rename_request(
        selected,
        source_scene=source_scene,
        proposed_label=normalize_display_label(draft_label),
    )


def _stable_entity_id(selected: Mapping[str, Any]) -> str:
    for key in ("id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
