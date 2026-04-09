from __future__ import annotations

from typing import Mapping

from engine.action_runtime import constants
from engine.action_runtime.registry import get_actions


def single_line_error(text: str) -> str:
    cleaned = str(text).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = " ".join(cleaned.splitlines())
    return " ".join(cleaned.split())


def invoke(
    action_name: str,
    window: object,
    *,
    actions: Mapping[str, constants.ActionHandler] | None = None,
    catch_exceptions: bool = True,
) -> tuple[bool, str]:
    table = dict(actions) if actions is not None else get_actions()
    name = str(action_name)
    handler = table.get(name)
    if handler is None:
        return False, f"{constants.UNKNOWN_ACTION_PREFIX} '{name}'"

    if not catch_exceptions:
        handler(window)
        return True, ""

    try:
        handler(window)
    except Exception as exc:  # noqa: BLE001  # REASON: action handlers are plugin-style callouts surfaced as user-facing errors
        message = single_line_error(str(exc))
        if message:
            return False, f"{type(exc).__name__}: {message}"
        return False, f"{type(exc).__name__}"

    return True, ""
