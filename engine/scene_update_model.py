from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class UpdateStep:
    PENDING_SCENE_LOAD = "pending_scene_load"
    PENDING_SCENE_CHANGE = "pending_scene_change"
    PRE_UPDATE = "pre_update"
    UPDATE_BEHAVIOUR = "update_behaviour"
    UPDATE_MOVEMENT = "update_movement"
    UPDATE_ANIMATION = "update_animation"
    LATE_UPDATE = "late_update"


@dataclass(frozen=True, slots=True)
class UpdateInputs:
    pending_scene_load: bool
    pending_scene_change: bool
    paused: bool


@dataclass(frozen=True, slots=True)
class QueueOp:
    kind: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    steps: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UpdateDiagnostics:
    step_count: int


def build_update_plan(inputs: UpdateInputs) -> UpdatePlan:
    if inputs.pending_scene_load:
        return UpdatePlan(steps=(UpdateStep.PENDING_SCENE_LOAD,))
    if inputs.pending_scene_change:
        return UpdatePlan(steps=(UpdateStep.PENDING_SCENE_CHANGE,))
    if inputs.paused:
        return UpdatePlan(steps=())
    return UpdatePlan(
        steps=(
            UpdateStep.PRE_UPDATE,
            UpdateStep.UPDATE_BEHAVIOUR,
            UpdateStep.UPDATE_MOVEMENT,
            UpdateStep.UPDATE_ANIMATION,
            UpdateStep.LATE_UPDATE,
        )
    )


def stable_entity_iteration_order(layers: Iterable[Iterable[object]]) -> list[object]:
    ordered: list[object] = []
    for layer in layers:
        ordered.extend(list(layer))
    return ordered


def plan_queue_ops(_queue_state: object | None) -> list[QueueOp]:
    return []
