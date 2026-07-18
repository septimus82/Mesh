"""Creator Mode display-label rename proposal live-op conversion."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_entity_rename_request import CreatorEntityRenameRequest


@dataclass(frozen=True, slots=True)
class CreatorEntityRenameLiveOpsResult:
    """Conversion result for a set_entity_display_label live-op proposal."""

    ok: bool
    ops: tuple[dict[str, object], ...] = ()
    preview_summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def build_creator_entity_rename_live_ops(
    request: CreatorEntityRenameRequest,
) -> CreatorEntityRenameLiveOpsResult:
    """Build the narrow live-op payload for a display-label rename."""

    if not request.ok:
        return CreatorEntityRenameLiveOpsResult(
            ok=False,
            errors=(request.reason or "Rename is unavailable.",),
        )

    preview = (
        f"Rename {request.entity_id} display label "
        f"from '{request.current_label}' to '{request.proposed_label}'"
    )
    op = {
        "type": "set_entity_display_label",
        "scene_path": request.source_scene,
        "entity_id": request.entity_id,
        "field": request.label_field,
        "expected_current_label": request.current_label,
        "label": request.proposed_label,
    }
    return CreatorEntityRenameLiveOpsResult(
        ok=True,
        ops=(op,),
        preview_summary=preview,
    )
