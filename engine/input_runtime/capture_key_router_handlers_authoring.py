from __future__ import annotations

from typing import Any


def dispatch_authoring_action(window: Any, action_id: str) -> bool:
    if action_id.startswith("capture.authoring."):
        return _handle_authoring_action(window, action_id)
    return False


def _handle_authoring_action(window: Any, action_id: str) -> bool:
    """Handle authoring selected entity nudge actions."""
    authoring_id = getattr(window, "authoring_selected_entity_id", None)
    if not authoring_id:
        return False

    if "_fine" in action_id:
        step = 1.0
    elif "_large" in action_id:
        step = 32.0
    else:
        step = 8.0

    dx = dy = 0.0
    if "nudge_left" in action_id:
        dx = -step
    elif "nudge_right" in action_id:
        dx = step
    elif "nudge_up" in action_id:
        dy = step
    elif "nudge_down" in action_id:
        dy = -step
    else:
        return False

    from engine.tooling_runtime.authoring_snippets import nudge_selected_entity  # noqa: PLC0415

    return bool(nudge_selected_entity(window, dx=dx, dy=dy))


__all__ = ["dispatch_authoring_action"]
