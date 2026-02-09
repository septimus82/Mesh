from __future__ import annotations

from typing import Any

from engine.scene_lifecycle_controller import handle_pending_scene_change, handle_pending_scene_load
from engine.scene_update_model import UpdateInputs, UpdateStep, build_update_plan


class SceneUpdateController:
    def handle_update(self, delta_time: float, controller: Any) -> None:
        inputs = UpdateInputs(
            pending_scene_load=bool(getattr(controller, "_pending_scene_path", None)),
            pending_scene_change=bool(getattr(controller, "_pending_scene_change", None)),
            paused=bool(getattr(controller.window, "paused", False)),
        )
        plan = build_update_plan(inputs)
        for step in plan.steps:
            if step == UpdateStep.PENDING_SCENE_LOAD:
                handle_pending_scene_load(controller)
                return
            if step == UpdateStep.PENDING_SCENE_CHANGE:
                handle_pending_scene_change(controller)
                return
            if step == UpdateStep.PRE_UPDATE:
                controller._pre_update_behaviour_stage(delta_time)
                continue
            if step == UpdateStep.UPDATE_BEHAVIOUR:
                controller._update_behaviour_stage(delta_time)
                continue
            if step == UpdateStep.UPDATE_MOVEMENT:
                controller._update_movement_stage(delta_time)
                continue
            if step == UpdateStep.UPDATE_ANIMATION:
                controller._update_animation_stage(delta_time)
                continue
            if step == UpdateStep.LATE_UPDATE:
                controller._late_update_stage(delta_time)
                continue

    def invalidate(self, _reason: str | None = None) -> None:
        return
