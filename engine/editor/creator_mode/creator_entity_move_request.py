"""Selection → one-grid-step movement request for Creator Mode."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_entity_move_actions import (
    DIRECTION_DOWN,
    DIRECTION_LEFT,
    DIRECTION_RIGHT,
    DIRECTION_UP,
)

_VALID_DIRECTIONS = frozenset(
    {DIRECTION_LEFT, DIRECTION_RIGHT, DIRECTION_UP, DIRECTION_DOWN}
)


@dataclass(frozen=True, slots=True)
class CreatorEntityMoveRequest:
    """Canonical movement request for staging a one-grid-step proposal."""

    ok: bool
    entity_id: str = ""
    entity_label: str = ""
    source_scene: str = ""
    direction: str = ""
    grid_step: float = 0.0
    from_x: float = 0.0
    from_y: float = 0.0
    to_x: float = 0.0
    to_y: float = 0.0
    reason: str = ""

    @property
    def available(self) -> bool:
        return bool(self.ok)


def resolve_entity_move_target(
    *,
    from_x: float,
    from_y: float,
    direction: str,
    grid_step: float,
) -> tuple[float, float]:
    """Return target world coordinates for one grid step.

    Arcade/world space is Y-up: larger Y is upward.
    """

    step = float(grid_step)
    x = float(from_x)
    y = float(from_y)
    key = str(direction or "").strip().lower()
    if key == DIRECTION_LEFT:
        return x - step, y
    if key == DIRECTION_RIGHT:
        return x + step, y
    if key == DIRECTION_UP:
        return x, y + step
    if key == DIRECTION_DOWN:
        return x, y - step
    raise ValueError(f"Unsupported movement direction '{direction}'")


def build_creator_entity_move_request(
    selected: Mapping[str, Any] | None,
    *,
    direction: str,
    source_scene: str,
    grid_step: float,
) -> CreatorEntityMoveRequest:
    """Build a movement request from a selected authored entity snapshot."""

    direction_key = str(direction or "").strip().lower()
    if direction_key not in _VALID_DIRECTIONS:
        return CreatorEntityMoveRequest(ok=False, reason="Unsupported movement direction.")

    if selected is None:
        return CreatorEntityMoveRequest(ok=False, reason="No entity is selected.")

    if not isinstance(selected, Mapping):
        return CreatorEntityMoveRequest(ok=False, reason="Selection is not an authored entity.")

    entity_id = _stable_entity_id(selected)
    if not entity_id:
        return CreatorEntityMoveRequest(
            ok=False,
            reason="Selected entity has no stable authored identity.",
        )

    if _is_runtime_or_helper(selected):
        return CreatorEntityMoveRequest(
            ok=False,
            entity_id=entity_id,
            reason="Selected entity is not part of the authored scene.",
        )

    position = _resolve_position(selected)
    if position is None:
        return CreatorEntityMoveRequest(
            ok=False,
            entity_id=entity_id,
            reason="Selected entity position cannot be resolved.",
        )

    try:
        step = float(grid_step)
    except (TypeError, ValueError):
        return CreatorEntityMoveRequest(
            ok=False,
            entity_id=entity_id,
            reason="Editor grid size is unavailable.",
        )
    if step <= 0.0:
        return CreatorEntityMoveRequest(
            ok=False,
            entity_id=entity_id,
            reason="Editor grid size is unavailable.",
        )

    scene = str(source_scene or "").strip()
    if not scene:
        return CreatorEntityMoveRequest(
            ok=False,
            entity_id=entity_id,
            reason="Current scene path is unavailable.",
        )

    from_x, from_y = position
    to_x, to_y = resolve_entity_move_target(
        from_x=from_x,
        from_y=from_y,
        direction=direction_key,
        grid_step=step,
    )
    label = _entity_label(selected, entity_id)
    return CreatorEntityMoveRequest(
        ok=True,
        entity_id=entity_id,
        entity_label=label,
        source_scene=scene,
        direction=direction_key,
        grid_step=step,
        from_x=from_x,
        from_y=from_y,
        to_x=to_x,
        to_y=to_y,
    )


def creator_entity_move_request_key(request: CreatorEntityMoveRequest) -> str:
    """Stable duplicate-staging key for one movement request."""

    if not request.ok:
        return ""
    return "|".join(
        (
            str(request.source_scene),
            str(request.entity_id),
            f"{float(request.from_x):.6f}",
            f"{float(request.from_y):.6f}",
            f"{float(request.to_x):.6f}",
            f"{float(request.to_y):.6f}",
            str(request.direction),
        )
    )


def _stable_entity_id(selected: Mapping[str, Any]) -> str:
    for key in ("id", "entity_id", "name", "mesh_name"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _entity_label(selected: Mapping[str, Any], entity_id: str) -> str:
    for key in ("name", "mesh_name", "id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity_id


def _resolve_position(selected: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        if "x" not in selected or "y" not in selected:
            return None
        x = float(selected["x"])
        y = float(selected["y"])
    except (TypeError, ValueError, KeyError):
        return None
    if x != x or y != y:  # NaN
        return None
    return x, y


def _is_runtime_or_helper(selected: Mapping[str, Any]) -> bool:
    if bool(selected.get("_runtime_generated")) or bool(selected.get("runtime_generated")):
        return True
    if bool(selected.get("_editor_only")) or bool(selected.get("editor_only")):
        return True
    kind = str(selected.get("kind") or selected.get("_kind") or "").strip().lower()
    if kind in {"runtime", "helper", "marker", "editor_helper"}:
        return True
    tags = selected.get("tags")
    if isinstance(tags, (list, tuple)) and "editor_helper" in tags:
        return True
    return False
