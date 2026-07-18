"""Creator Mode duplicate proposal live-op conversion."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_entity_duplicate_request import CreatorEntityDuplicateRequest


@dataclass(frozen=True, slots=True)
class CreatorEntityDuplicateLiveOpsResult:
    """Conversion result for a duplicate_entity live-op proposal."""

    ok: bool
    ops: tuple[dict[str, object], ...] = ()
    preview_summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_creator_entity_duplicate_live_ops(
    request: CreatorEntityDuplicateRequest,
) -> CreatorEntityDuplicateLiveOpsResult:
    """Build the narrow live-op payload for selected entity duplication."""

    if not request.ok or request.source_payload is None:
        return CreatorEntityDuplicateLiveOpsResult(
            ok=False,
            errors=(request.reason or "Duplicate is unavailable.",),
        )
    summary = (
        f"Duplicate {request.source_entity_id} as {request.duplicate_entity_id} "
        f"at ({request.to_x:g}, {request.to_y:g})"
    )
    op = {
        "type": "duplicate_entity",
        "scene_path": request.source_scene,
        "source_entity_id": request.source_entity_id,
        "expected_source_fingerprint": request.source_fingerprint,
        "expected_source_x": float(request.from_x),
        "expected_source_y": float(request.from_y),
        "duplicate_entity_id": request.duplicate_entity_id,
        "x": float(request.to_x),
        "y": float(request.to_y),
        "dx": float(request.dx),
        "dy": float(request.dy),
    }
    return CreatorEntityDuplicateLiveOpsResult(ok=True, ops=(op,), preview_summary=summary)
