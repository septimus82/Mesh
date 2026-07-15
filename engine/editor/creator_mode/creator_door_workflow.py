"""Pure Creator Mode door workflow coordinator."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_door_plan import (
    CreatorDoorPlan,
    CreatorDoorPlanRequest,
    build_creator_door_plan,
)
from .creator_door_preview import CreatorDoorPreviewModel, build_creator_door_preview


@dataclass(frozen=True, slots=True)
class CreatorDoorWorkflowRequest:
    """Friendly door intent for plan and preview construction."""

    source_scene: str
    destination_scene: str
    destination_spawn_id: str = ""
    door_name: str = ""
    source_entity_id: str = ""
    locked: bool = False
    required_flag: str = ""
    trigger: str = "interact"
    transition_behaviour: str = "SceneTransition"
    scene_exit_listen_event: str = ""
    interactable_event: str = ""
    entity_require_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CreatorDoorWorkflowModel:
    """Read-only door workflow result for future Creator Mode UI."""

    plan: CreatorDoorPlan
    preview: CreatorDoorPreviewModel


def build_creator_door_workflow(
    request: CreatorDoorWorkflowRequest,
) -> CreatorDoorWorkflowModel:
    """Build both the pure door plan and its read-only preview."""

    return build_creator_door_workflow_from_plan_request(
        CreatorDoorPlanRequest(
            source_scene=request.source_scene,
            destination_scene=request.destination_scene,
            destination_spawn_id=request.destination_spawn_id,
            door_name=request.door_name,
            source_entity_id=request.source_entity_id,
            locked=request.locked,
            required_flag=request.required_flag,
            trigger=request.trigger,
            transition_behaviour=request.transition_behaviour,
            scene_exit_listen_event=request.scene_exit_listen_event,
            interactable_event=request.interactable_event,
            entity_require_flags=request.entity_require_flags,
        )
    )


def build_creator_door_workflow_from_plan_request(
    request: CreatorDoorPlanRequest,
) -> CreatorDoorWorkflowModel:
    """Build a door workflow from an existing pure plan request."""

    plan = build_creator_door_plan(request)
    preview = build_creator_door_preview(plan)
    return CreatorDoorWorkflowModel(plan=plan, preview=preview)
