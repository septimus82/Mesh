"""Creator Mode entity-move proposal staging adapter."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .creator_entity_move_live_ops import build_creator_entity_move_live_ops
from .creator_entity_move_request import CreatorEntityMoveRequest


@dataclass(frozen=True, slots=True)
class CreatorEntityMoveStagingResult:
    """Normalized result for staging a movement proposal through an injected bridge."""

    ok: bool
    proposal_id: str = ""
    preview_summary: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def stage_creator_entity_move_proposal(
    request: CreatorEntityMoveRequest,
    bridge: object,
) -> CreatorEntityMoveStagingResult:
    """Stage movement live ops through a bridge-like object without applying them."""

    live_ops = build_creator_entity_move_live_ops(request)
    if not live_ops.ok:
        return CreatorEntityMoveStagingResult(
            ok=False,
            errors=tuple(live_ops.errors),
            warnings=tuple(live_ops.warnings),
        )

    stage = getattr(bridge, "stage_pending_proposal", None)
    if not callable(stage):
        return CreatorEntityMoveStagingResult(
            ok=False,
            errors=("Proposal bridge is unavailable.",),
            warnings=tuple(live_ops.warnings),
        )

    try:
        result = stage(copy.deepcopy(list(live_ops.ops)))
    except Exception:  # noqa: BLE001  # REASON: creator staging must fail closed for UI callers.
        return CreatorEntityMoveStagingResult(
            ok=False,
            errors=("Failed to stage movement proposal.",),
            warnings=tuple(live_ops.warnings),
        )

    return _normalize_bridge_result(
        result,
        adapter_warnings=live_ops.warnings,
        fallback_summary=live_ops.preview_summary,
    )


def _normalize_bridge_result(
    result: object,
    *,
    adapter_warnings: tuple[str, ...],
    fallback_summary: str,
) -> CreatorEntityMoveStagingResult:
    if not isinstance(result, Mapping):
        return CreatorEntityMoveStagingResult(
            ok=False,
            errors=("Proposal bridge returned an invalid result.",),
            warnings=adapter_warnings,
        )

    warnings = (*adapter_warnings, *_strings(result.get("warnings")))
    ok = bool(result.get("ok") is True or result.get("success") is True)
    if ok:
        return CreatorEntityMoveStagingResult(
            ok=True,
            proposal_id=_text(result.get("proposal_id") or result.get("id")),
            preview_summary=_preview_summary(result) or fallback_summary,
            errors=(),
            warnings=warnings,
        )

    message = _first_text(
        result.get("message"),
        result.get("error"),
        result.get("reason"),
        fallback="Proposal bridge failed to stage movement proposal.",
    )
    return CreatorEntityMoveStagingResult(
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
