"""Stage Creator Mode selected-entity opacity proposals."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .creator_entity_opacity_live_ops import build_creator_entity_opacity_live_ops
from .creator_entity_opacity_request import CreatorEntityOpacityRequest


@dataclass(frozen=True, slots=True)
class CreatorEntityOpacityStagingResult:
    """Result for staging an opacity proposal."""

    ok: bool
    proposal_id: str = ""
    summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def stage_creator_entity_opacity_proposal(
    request: CreatorEntityOpacityRequest,
    bridge: object | None,
) -> CreatorEntityOpacityStagingResult:
    """Stage an opacity proposal through the official bridge."""

    live_ops = build_creator_entity_opacity_live_ops(request)
    if not live_ops.ok:
        return CreatorEntityOpacityStagingResult(
            ok=False,
            errors=tuple(live_ops.errors),
            warnings=tuple(live_ops.warnings),
        )

    stage = getattr(bridge, "stage_pending_proposal", None)
    if not callable(stage):
        return CreatorEntityOpacityStagingResult(
            ok=False,
            errors=("Proposal bridge is unavailable.",),
            warnings=tuple(live_ops.warnings),
        )

    result = stage(copy.deepcopy(list(live_ops.ops)))
    if not isinstance(result, dict):
        return CreatorEntityOpacityStagingResult(
            ok=False,
            errors=("Proposal bridge returned an invalid result.",),
            warnings=tuple(live_ops.warnings),
        )
    if result.get("ok") is not True:
        return CreatorEntityOpacityStagingResult(
            ok=False,
            errors=(_bridge_message(result, fallback="Failed to stage opacity proposal."),),
            warnings=tuple(live_ops.warnings),
        )

    return CreatorEntityOpacityStagingResult(
        ok=True,
        proposal_id=str(result.get("proposal_id") or "").strip(),
        summary=str(result.get("preview") or live_ops.preview_summary),
        warnings=tuple(live_ops.warnings),
    )


def _bridge_message(result: dict[str, Any], *, fallback: str) -> str:
    for key in ("message", "reason", "error"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback
