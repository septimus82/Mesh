"""Creator Mode selected-entity opacity panel model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_entity_opacity_request import (
    CreatorEntityOpacityRequest,
    alpha_to_draft_percent,
    build_creator_entity_opacity_request,
    creator_entity_opacity_request_key,
    format_opacity_percent,
    resolve_alpha_state,
)

ENTITY_OPACITY_DRAFT_ACTION_ID = "entity.opacity.draft"
ENTITY_OPACITY_STAGE_ACTION_ID = "entity.opacity.stage"
ENTITY_OPACITY_PRESET_ACTION_PREFIX = "entity.opacity.preset."
ENTITY_OPACITY_PRESET_VALUES: tuple[int, ...] = (0, 25, 50, 75, 100)


@dataclass(frozen=True, slots=True)
class CreatorEntityOpacityPanelAction:
    """One opacity action with enablement and hit-test identity."""

    label: str
    action_id: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorEntityOpacityPanelModel:
    """Compact selected-entity opacity section."""

    title: str
    available: bool
    entity_id: str
    current_percent: str
    draft_percent: str
    focused: bool
    authored_state: str
    reason: str
    action: CreatorEntityOpacityPanelAction
    preset_actions: tuple[CreatorEntityOpacityPanelAction, ...]


def build_creator_entity_opacity_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    draft_percent: str,
    bridge: object | None,
    focused: bool = False,
    duplicate_keys: Mapping[str, str] | None = None,
) -> CreatorEntityOpacityPanelModel:
    """Build opacity panel state for the current selection."""

    alpha_state = resolve_alpha_state(selected) if isinstance(selected, Mapping) else None
    if alpha_state is not None and str(draft_percent or "") == "":
        draft_percent = alpha_to_draft_percent(alpha_state.effective_value)

    request = build_creator_entity_opacity_request(
        selected,
        source_scene=source_scene,
        draft_percent=draft_percent,
    )
    bridge_ok = callable(getattr(bridge, "stage_pending_proposal", None))
    entity_id = request.entity_id
    if not entity_id and isinstance(selected, Mapping):
        entity_id = _stable_entity_id(selected)

    current_percent = "Current: --"
    authored_state = "Authored alpha: malformed"
    if alpha_state is not None:
        current_percent = f"Current: {format_opacity_percent(alpha_state.effective_value)}"
        authored_state = (
            f"Authored alpha: {alpha_state.authored_value:g}"
            if alpha_state.present and alpha_state.authored_value is not None
            else "Authored alpha: omitted -> 1.0"
        )

    action = CreatorEntityOpacityPanelAction(
        label="Stage Opacity Proposal",
        action_id=ENTITY_OPACITY_STAGE_ACTION_ID,
        enabled=False,
        reason=request.reason or "Opacity proposals are unavailable for this entity type.",
    )
    if request.ok and not bridge_ok:
        action = CreatorEntityOpacityPanelAction(
            label="Stage Opacity Proposal",
            action_id=ENTITY_OPACITY_STAGE_ACTION_ID,
            enabled=False,
            reason="Proposal bridge is unavailable.",
        )
    elif request.ok:
        staged_id = ""
        request_key = creator_entity_opacity_request_key(request)
        if isinstance(duplicate_keys, Mapping):
            staged_id = str(duplicate_keys.get(request_key) or "").strip()
        if staged_id:
            action = CreatorEntityOpacityPanelAction(
                label="Stage Opacity Proposal",
                action_id=ENTITY_OPACITY_STAGE_ACTION_ID,
                enabled=False,
                reason=f"Already staged: {staged_id}",
            )
        else:
            action = CreatorEntityOpacityPanelAction(
                label="Stage Opacity Proposal",
                action_id=ENTITY_OPACITY_STAGE_ACTION_ID,
                enabled=True,
                reason="",
            )

    preset_actions = tuple(
        CreatorEntityOpacityPanelAction(
            label=f"{value}%",
            action_id=f"{ENTITY_OPACITY_PRESET_ACTION_PREFIX}{value}",
            enabled=bool(entity_id and bridge_ok and alpha_state is not None),
        )
        for value in ENTITY_OPACITY_PRESET_VALUES
    )
    return CreatorEntityOpacityPanelModel(
        title="Opacity",
        available=bool(request.ok and bridge_ok),
        entity_id=entity_id,
        current_percent=current_percent,
        draft_percent=str(draft_percent or ""),
        focused=bool(focused),
        authored_state=authored_state,
        reason=action.reason,
        action=action,
        preset_actions=preset_actions,
    )


def request_for_opacity_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    draft_percent: str,
) -> CreatorEntityOpacityRequest:
    """Build the current opacity request from the panel draft."""

    return build_creator_entity_opacity_request(
        selected,
        source_scene=source_scene,
        draft_percent=draft_percent,
    )


def preset_percent_for_action(action_id: str) -> str:
    """Return the percent text represented by an opacity preset action."""

    prefix = ENTITY_OPACITY_PRESET_ACTION_PREFIX
    text = str(action_id or "").strip()
    if not text.startswith(prefix):
        return ""
    value = text[len(prefix):]
    return value if value in {str(item) for item in ENTITY_OPACITY_PRESET_VALUES} else ""


def _stable_entity_id(selected: Mapping[str, Any]) -> str:
    for key in ("id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
