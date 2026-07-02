"""Creator Mode door proposal staging adapter."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_door_live_ops import build_creator_door_live_ops
from .creator_door_workflow import CreatorDoorWorkflowModel


@dataclass(frozen=True, slots=True)
class CreatorDoorStagingResult:
    """Normalized result for staging a door proposal through an injected bridge."""

    ok: bool
    proposal_id: str = ""
    preview_summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def stage_creator_door_proposal(
    workflow: CreatorDoorWorkflowModel,
    bridge: object,
) -> CreatorDoorStagingResult:
    """Stage door live ops through a bridge-like object without applying them."""

    live_ops = build_creator_door_live_ops(workflow)
    if not live_ops.ok:
        return CreatorDoorStagingResult(
            ok=False,
            errors=tuple(live_ops.errors),
            warnings=tuple(live_ops.warnings),
        )

    stage = getattr(bridge, "stage_pending_proposal", None)
    if not callable(stage):
        return CreatorDoorStagingResult(
            ok=False,
            errors=("Proposal bridge is unavailable.",),
            warnings=tuple(live_ops.warnings),
        )

    try:
        result = stage(copy.deepcopy(list(live_ops.ops)))
    except Exception:  # noqa: BLE001  # REASON: creator staging must fail closed for UI callers.
        return CreatorDoorStagingResult(
            ok=False,
            errors=("Failed to stage door proposal.",),
            warnings=tuple(live_ops.warnings),
        )

    return _normalize_bridge_result(result, adapter_warnings=live_ops.warnings)


def _normalize_bridge_result(
    result: object,
    *,
    adapter_warnings: tuple[str, ...],
) -> CreatorDoorStagingResult:
    if not isinstance(result, Mapping):
        return CreatorDoorStagingResult(
            ok=False,
            errors=("Proposal bridge returned an invalid result.",),
            warnings=adapter_warnings,
        )

    warnings = (*adapter_warnings, *_strings(result.get("warnings")))
    ok = bool(result.get("ok") is True or result.get("success") is True)
    if ok:
        return CreatorDoorStagingResult(
            ok=True,
            proposal_id=_text(result.get("proposal_id") or result.get("id")),
            preview_summary=_preview_summary(result),
            errors=(),
            warnings=warnings,
        )

    message = _first_text(
        result.get("message"),
        result.get("error"),
        result.get("reason"),
        fallback="Proposal bridge failed to stage door proposal.",
    )
    return CreatorDoorStagingResult(
        ok=False,
        errors=(message,),
        warnings=warnings,
    )


def _preview_summary(result: Mapping[str, Any]) -> str:
    proposal = result.get("proposal")
    if isinstance(proposal, Mapping):
        summary = _text(proposal.get("preview_summary"))
        if summary:
            return summary
    return _first_text(
        result.get("preview_summary"),
        result.get("preview"),
        fallback="",
    )


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, (list, tuple)):
        return tuple(text for item in value if (text := _text(item)))
    return ()


def _first_text(*values: object, fallback: str) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return fallback


def _text(value: object) -> str:
    return str(value or "").strip()
