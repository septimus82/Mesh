"""Creator Mode overlay click dispatch."""

from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from .creator_entity_duplicate_panel import ENTITY_DUPLICATE_STAGE_ACTION_ID
from .creator_entity_move_actions import ENTITY_MOVE_ACTION_ID_SET
from .creator_entity_opacity_panel import (
    ENTITY_OPACITY_DRAFT_ACTION_ID,
    ENTITY_OPACITY_PRESET_ACTION_PREFIX,
    ENTITY_OPACITY_STAGE_ACTION_ID,
)
from .creator_entity_rename_panel import (
    ENTITY_RENAME_DRAFT_ACTION_ID,
    ENTITY_RENAME_STAGE_ACTION_ID,
)
from .creator_overlay import build_creator_overlay_model
from .creator_overlay_renderer import (
    DOOR_STAGE_PROPOSAL_ACTION_ID,
    STAGE_PROPOSAL_LABEL,
    build_creator_overlay_draw_commands,
    hit_test_creator_overlay_click,
)
from .creator_proposal_handoff import PROPOSAL_OPEN_INBOX_ACTION_ID

_LEFT_BUTTON = getattr(getattr(optional_arcade, "arcade", None), "MOUSE_BUTTON_LEFT", 1)


def try_handle_creator_mode_overlay_click(
    editor: Any,
    x: float,
    y: float,
    button: int,
    modifiers: int = 0,  # noqa: ARG001
) -> bool:
    """Return True when a Creator Mode overlay click action was handled."""

    if int(button) != int(_LEFT_BUTTON):
        return False
    if not getattr(editor, "active", False):
        return False

    creator = getattr(editor, "creator_mode", None)
    if creator is None or not getattr(creator, "active", False):
        return False

    handler = getattr(creator, "handle_overlay_click", None)
    if not callable(handler):
        return False

    return handler(float(x), float(y)) is not None


def stage_proposal_action_enabled(model: Any) -> bool:
    """True when the door panel exposes an enabled Stage Proposal action."""

    panel = getattr(model, "door_panel", None)
    if panel is None:
        return False
    for action in getattr(panel, "actions", ()):
        if str(getattr(action, "label", "")) == STAGE_PROPOSAL_LABEL and bool(
            getattr(action, "enabled", False)
        ):
            return True
    return False


def entity_move_action_enabled(model: Any, action_id: str) -> bool:
    """True when the movement panel exposes the given enabled action."""

    panel = getattr(model, "movement_panel", None)
    if panel is None:
        return False
    target = str(action_id or "").strip()
    if target not in ENTITY_MOVE_ACTION_ID_SET:
        return False
    for action in getattr(panel, "actions", ()):
        if str(getattr(action, "action_id", "") or "") == target and bool(
            getattr(action, "enabled", False)
        ):
            return True
    return False


def proposal_open_inbox_action_enabled(model: Any) -> bool:
    """True when the proposal handoff exposes the official inbox action."""

    handoff = getattr(model, "proposal_handoff", None)
    return (
        bool(getattr(handoff, "enabled", False))
        and str(getattr(handoff, "action_id", "") or "") == PROPOSAL_OPEN_INBOX_ACTION_ID
        and int(getattr(handoff, "pending_count", 0) or 0) > 0
    )


def entity_rename_action_enabled(model: Any) -> bool:
    """True when the rename panel exposes an enabled Stage Rename action."""

    panel = getattr(model, "rename_panel", None)
    action = getattr(panel, "action", None) if panel is not None else None
    return (
        action is not None
        and str(getattr(action, "action_id", "") or "") == ENTITY_RENAME_STAGE_ACTION_ID
        and bool(getattr(action, "enabled", False))
    )


def entity_opacity_action_enabled(model: Any, action_id: str) -> bool:
    """True when the opacity panel exposes the given enabled action."""

    panel = getattr(model, "opacity_panel", None)
    if panel is None:
        return False
    target = str(action_id or "").strip()
    if target == ENTITY_OPACITY_DRAFT_ACTION_ID:
        return bool(getattr(panel, "entity_id", "")) and any(
            bool(getattr(action, "enabled", False))
            for action in getattr(panel, "preset_actions", ()) or ()
        )
    if target == ENTITY_OPACITY_STAGE_ACTION_ID:
        action = getattr(panel, "action", None)
        return (
            action is not None
            and str(getattr(action, "action_id", "") or "") == ENTITY_OPACITY_STAGE_ACTION_ID
            and bool(getattr(action, "enabled", False))
        )
    if target.startswith(ENTITY_OPACITY_PRESET_ACTION_PREFIX):
        for action in getattr(panel, "preset_actions", ()) or ():
            if str(getattr(action, "action_id", "") or "") == target:
                return bool(getattr(action, "enabled", False))
    return False


def entity_duplicate_action_enabled(model: Any) -> bool:
    """True when the duplicate panel exposes an enabled Stage action."""

    panel = getattr(model, "duplicate_panel", None)
    action = getattr(panel, "action", None) if panel is not None else None
    return (
        action is not None
        and str(getattr(action, "action_id", "") or "") == ENTITY_DUPLICATE_STAGE_ACTION_ID
        and bool(getattr(action, "enabled", False))
    )


def resolve_creator_overlay_click_action(
    creator: Any,
    x: float,
    y: float,
) -> str | None:
    """Hit-test the current Creator Mode overlay for a clickable action id."""

    if creator is None or not getattr(creator, "active", False):
        return None

    editor = getattr(creator, "_editor", None)
    window = getattr(editor, "window", None)
    width = float(getattr(window, "width", 1280) or 1280)
    height = float(getattr(window, "height", 720) or 720)
    snapshot = creator.build_snapshot()
    model = build_creator_overlay_model(snapshot)
    if not model.active:
        return None

    commands = build_creator_overlay_draw_commands(model, width, height)
    action_id = hit_test_creator_overlay_click(commands, float(x), float(y))
    if action_id == DOOR_STAGE_PROPOSAL_ACTION_ID:
        if not stage_proposal_action_enabled(model):
            return None
        return action_id
    if action_id in ENTITY_MOVE_ACTION_ID_SET:
        if not entity_move_action_enabled(model, action_id):
            return None
        return action_id
    if action_id == ENTITY_RENAME_DRAFT_ACTION_ID:
        panel = getattr(model, "rename_panel", None)
        action = getattr(panel, "action", None) if panel is not None else None
        if action is not None and str(getattr(action, "reason", "") or "") == "Proposal bridge is unavailable.":
            return None
        return action_id
    if action_id == ENTITY_RENAME_STAGE_ACTION_ID:
        if not entity_rename_action_enabled(model):
            return None
        return action_id
    if action_id in {ENTITY_OPACITY_DRAFT_ACTION_ID, ENTITY_OPACITY_STAGE_ACTION_ID} or str(
        action_id or ""
    ).startswith(ENTITY_OPACITY_PRESET_ACTION_PREFIX):
        if not entity_opacity_action_enabled(model, action_id):
            return None
        return action_id
    if action_id == ENTITY_DUPLICATE_STAGE_ACTION_ID:
        if not entity_duplicate_action_enabled(model):
            return None
        return action_id
    if action_id == PROPOSAL_OPEN_INBOX_ACTION_ID:
        if not proposal_open_inbox_action_enabled(model):
            return None
        return action_id
    return None
