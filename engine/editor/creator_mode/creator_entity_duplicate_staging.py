"""Stage Creator Mode selected-entity duplicate proposals."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .creator_entity_duplicate_live_ops import build_creator_entity_duplicate_live_ops
from .creator_entity_duplicate_request import CreatorEntityDuplicateRequest


@dataclass(frozen=True, slots=True)
class CreatorEntityDuplicateStagingResult:
    """Result for staging a duplicate proposal."""

    ok: bool
    proposal_id: str = ""
    summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def stage_creator_entity_duplicate_proposal(
    request: CreatorEntityDuplicateRequest,
    bridge: object | None,
) -> CreatorEntityDuplicateStagingResult:
    """Stage a duplicate proposal through the official bridge."""

    live_ops = build_creator_entity_duplicate_live_ops(request)
    if not live_ops.ok:
        return CreatorEntityDuplicateStagingResult(
            ok=False,
            errors=tuple(live_ops.errors),
            warnings=tuple(live_ops.warnings),
        )
    stage = getattr(bridge, "stage_pending_proposal", None)
    if not callable(stage):
        return CreatorEntityDuplicateStagingResult(
            ok=False,
            errors=("Proposal bridge is unavailable.",),
            warnings=tuple(live_ops.warnings),
        )
    result = stage(copy.deepcopy(list(live_ops.ops)))
    if not isinstance(result, dict):
        return CreatorEntityDuplicateStagingResult(
            ok=False,
            errors=("Proposal bridge returned an invalid result.",),
            warnings=tuple(live_ops.warnings),
        )
    if result.get("ok") is not True:
        return CreatorEntityDuplicateStagingResult(
            ok=False,
            errors=(_bridge_message(result, fallback="Failed to stage duplicate proposal."),),
            warnings=tuple(live_ops.warnings),
        )
    return CreatorEntityDuplicateStagingResult(
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
