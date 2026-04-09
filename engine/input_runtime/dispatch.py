from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable

from engine.input_runtime import capture


if TYPE_CHECKING:
    from engine.input_controller import InputController


def update(
    controller: "InputController",
    delta_time: float,
    *,
    dispatch_action: Callable[[object, str], bool],
    log_once_with_counter: Callable[[str, str], None],
    logger: object,
    log_once_set: set[str],
) -> None:
    updater = getattr(controller.manager, "update", None)
    if callable(updater):
        try:
            updater(delta_time)
        except Exception as exc:  # noqa: BLE001  # REASON: manager update failures should log once and keep later input dispatch checks running
            if "input_update" not in log_once_set:
                error = getattr(logger, "error", None)
                if callable(error):
                    error("Input update failed: %s", exc, exc_info=True)
                log_once_set.add("input_update")

    pressed = getattr(controller.manager, "was_action_pressed", None)
    if not callable(pressed):
        return

    ui_blocked = capture.ui_blocks_input(controller)

    for action_name in controller.manager.get_bound_action_names():
        if not pressed(action_name):
            continue

        if ui_blocked and not capture.should_dispatch_action_when_blocked(action_name):
            continue

        if (
            not controller._first_input_toast_fired
            and str(action_name) in capture.GAMEPLAY_ACTIONS
            and os.environ.get("MESH_ACTIVE_PRESET") == "golden_slice_variant_d"
        ):
            controller._first_input_toast_fired = True
            controller.window.player_hud.enqueue_toast("GO!")

        if not dispatch_action(controller.window, action_name):
            log_once_with_counter(
                f"input_unknown_action:{action_name}",
                f"[Mesh][Input] Unknown action '{action_name}'",
            )
