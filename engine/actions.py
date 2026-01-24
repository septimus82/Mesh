from __future__ import annotations

from engine.action_runtime.constants import ActionHandler as ActionHandler
from engine.action_runtime.registry import (
    _toggle_shadowcast_debug as _toggle_shadowcast_debug,
    _toggle_shadowmask as _toggle_shadowmask,
    dispatch_action as dispatch_action,
    get_actions as _get_actions,
    get_required_actions as _get_required_actions,
    list_actions as list_actions,
    validate_bound_actions as validate_bound_actions,
)

ACTIONS: dict[str, ActionHandler] = _get_actions()
REQUIRED_ACTIONS: set[str] = _get_required_actions()
