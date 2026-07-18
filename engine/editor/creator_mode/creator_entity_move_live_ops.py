"""Pure Creator Mode entity-move request to live-op adapter."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_entity_move_request import CreatorEntityMoveRequest


@dataclass(frozen=True, slots=True)
class CreatorEntityMoveLiveOpsResult:
    """Conversion result for a move_entity live-op proposal."""

    ok: bool
    ops: tuple[dict[str, object], ...]
    preview_summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_creator_entity_move_live_ops(
    request: CreatorEntityMoveRequest,
) -> CreatorEntityMoveLiveOpsResult:
    """Convert a movement request into canonical live-op dictionaries."""

    if not request.ok:
        return CreatorEntityMoveLiveOpsResult(
            ok=False,
            ops=(),
            errors=(request.reason or "Movement request is unavailable.",),
        )

    op: dict[str, object] = {
        "type": "move_entity",
        "scene_path": str(request.source_scene),
        "entity_id": str(request.entity_id),
        "x": float(request.to_x),
        "y": float(request.to_y),
        "from_x": float(request.from_x),
        "from_y": float(request.from_y),
        "direction": str(request.direction),
        "grid_step": float(request.grid_step),
    }
    label = str(request.entity_label or request.entity_id)
    summary = (
        f"Move {label} from ({request.from_x:g}, {request.from_y:g}) "
        f"to ({request.to_x:g}, {request.to_y:g})"
    )
    return CreatorEntityMoveLiveOpsResult(
        ok=True,
        ops=(op,),
        preview_summary=summary,
        errors=(),
        warnings=(),
    )
