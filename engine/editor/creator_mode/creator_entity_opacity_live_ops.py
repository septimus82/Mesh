"""Creator Mode opacity proposal live-op conversion."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_entity_opacity_request import (
    CreatorEntityOpacityRequest,
    format_opacity_percent,
)


@dataclass(frozen=True, slots=True)
class CreatorEntityOpacityLiveOpsResult:
    """Conversion result for a set_entity_alpha live-op proposal."""

    ok: bool
    ops: tuple[dict[str, object], ...] = ()
    preview_summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_creator_entity_opacity_live_ops(
    request: CreatorEntityOpacityRequest,
) -> CreatorEntityOpacityLiveOpsResult:
    """Build the narrow live-op payload for authored alpha changes."""

    if not request.ok or request.current_alpha is None:
        return CreatorEntityOpacityLiveOpsResult(
            ok=False,
            errors=(request.reason or "Opacity is unavailable.",),
        )

    current = request.current_alpha
    before = format_opacity_percent(current.effective_value)
    after = format_opacity_percent(request.proposed_alpha)
    summary = f"Change {request.entity_id} opacity from {before} to {after}"
    op = {
        "type": "set_entity_alpha",
        "scene_path": request.source_scene,
        "entity_id": request.entity_id,
        "field": "alpha",
        "expected_current_alpha": current.to_payload(),
        "alpha": float(request.proposed_alpha),
    }
    return CreatorEntityOpacityLiveOpsResult(
        ok=True,
        ops=(op,),
        preview_summary=summary,
    )
