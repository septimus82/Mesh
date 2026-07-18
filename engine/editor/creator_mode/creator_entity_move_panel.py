"""Read-only Creator Mode selected-entity movement panel model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_entity_move_actions import (
    ACTION_ID_BY_DIRECTION,
    DIRECTION_BY_ACTION_ID,
    DIRECTION_DOWN,
    DIRECTION_LABELS,
    DIRECTION_LEFT,
    DIRECTION_RIGHT,
    DIRECTION_UP,
    ENTITY_MOVE_ACTION_IDS,
)
from .creator_entity_move_request import (
    CreatorEntityMoveRequest,
    build_creator_entity_move_request,
)


@dataclass(frozen=True, slots=True)
class CreatorEntityMovePanelAction:
    """One movement action with enablement and hit-test identity."""

    label: str
    action_id: str
    direction: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorEntityMovePanelModel:
    """Compact selected-entity movement section for the Creator overlay."""

    title: str
    available: bool
    current_position_text: str
    grid_step_text: str
    reason: str
    entity_id: str
    source_scene: str
    from_x: float
    from_y: float
    grid_step: float
    actions: tuple[CreatorEntityMovePanelAction, ...]


def build_creator_entity_move_panel(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    grid_step: float,
    bridge: object | None,
    duplicate_keys: Mapping[str, str] | None = None,
) -> CreatorEntityMovePanelModel:
    """Build movement panel state for the current selection."""

    probe = build_creator_entity_move_request(
        selected,
        direction=DIRECTION_RIGHT,
        source_scene=source_scene,
        grid_step=grid_step,
    )
    bridge_ok = callable(getattr(bridge, "stage_pending_proposal", None))
    if not probe.ok:
        return CreatorEntityMovePanelModel(
            title="Movement",
            available=False,
            current_position_text="Current: —",
            grid_step_text=_grid_step_text(grid_step),
            reason=probe.reason or "Movement is unavailable.",
            entity_id=probe.entity_id,
            source_scene=str(source_scene or ""),
            from_x=0.0,
            from_y=0.0,
            grid_step=_safe_grid(grid_step),
            actions=_disabled_actions(probe.reason or "Movement is unavailable."),
        )

    if not bridge_ok:
        reason = "Proposal bridge is unavailable."
        return CreatorEntityMovePanelModel(
            title="Movement",
            available=False,
            current_position_text=_current_position_text(probe.from_x, probe.from_y),
            grid_step_text=_grid_step_text(probe.grid_step),
            reason=reason,
            entity_id=probe.entity_id,
            source_scene=probe.source_scene,
            from_x=probe.from_x,
            from_y=probe.from_y,
            grid_step=probe.grid_step,
            actions=_disabled_actions(reason),
        )

    actions: list[CreatorEntityMovePanelAction] = []
    for direction in (DIRECTION_LEFT, DIRECTION_RIGHT, DIRECTION_UP, DIRECTION_DOWN):
        request = build_creator_entity_move_request(
            selected,
            direction=direction,
            source_scene=source_scene,
            grid_step=grid_step,
        )
        action_id = ACTION_ID_BY_DIRECTION[direction]
        label = DIRECTION_LABELS[direction]
        if not request.ok:
            actions.append(
                CreatorEntityMovePanelAction(
                    label=label,
                    action_id=action_id,
                    direction=direction,
                    enabled=False,
                    reason=request.reason or "Movement is unavailable.",
                )
            )
            continue

        from .creator_entity_move_request import creator_entity_move_request_key  # noqa: PLC0415

        request_key = creator_entity_move_request_key(request)
        staged_id = ""
        if isinstance(duplicate_keys, Mapping):
            staged_id = str(duplicate_keys.get(request_key) or "").strip()
        if staged_id:
            actions.append(
                CreatorEntityMovePanelAction(
                    label=label,
                    action_id=action_id,
                    direction=direction,
                    enabled=False,
                    reason=f"Already staged: {staged_id}",
                )
            )
            continue

        actions.append(
            CreatorEntityMovePanelAction(
                label=label,
                action_id=action_id,
                direction=direction,
                enabled=True,
                reason="",
            )
        )

    return CreatorEntityMovePanelModel(
        title="Movement",
        available=True,
        current_position_text=_current_position_text(probe.from_x, probe.from_y),
        grid_step_text=_grid_step_text(probe.grid_step),
        reason="",
        entity_id=probe.entity_id,
        source_scene=probe.source_scene,
        from_x=probe.from_x,
        from_y=probe.from_y,
        grid_step=probe.grid_step,
        actions=tuple(actions),
    )


def request_for_panel_action(
    selected: Mapping[str, Any] | None,
    *,
    action_id: str,
    source_scene: str,
    grid_step: float,
) -> CreatorEntityMoveRequest:
    """Build the movement request for a clicked action ID."""

    direction = DIRECTION_BY_ACTION_ID.get(str(action_id or "").strip(), "")
    return build_creator_entity_move_request(
        selected,
        direction=direction,
        source_scene=source_scene,
        grid_step=grid_step,
    )


def _disabled_actions(reason: str) -> tuple[CreatorEntityMovePanelAction, ...]:
    return tuple(
        CreatorEntityMovePanelAction(
            label=DIRECTION_LABELS[DIRECTION_BY_ACTION_ID[action_id]],
            action_id=action_id,
            direction=DIRECTION_BY_ACTION_ID[action_id],
            enabled=False,
            reason=reason,
        )
        for action_id in ENTITY_MOVE_ACTION_IDS
    )


def _current_position_text(x: float, y: float) -> str:
    return f"Current: {float(x):g}, {float(y):g}"


def _grid_step_text(grid_step: float) -> str:
    step = _safe_grid(grid_step)
    if step <= 0.0:
        return "Grid step: —"
    return f"Grid step: {step:g}"


def _safe_grid(grid_step: float) -> float:
    try:
        value = float(grid_step)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0.0 else 0.0
