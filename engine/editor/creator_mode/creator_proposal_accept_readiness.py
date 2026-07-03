"""Read-only proposal accept/reject readiness for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_proposal_status import (
    CreatorProposalListRow,
    CreatorProposalStatusModel,
    build_creator_proposal_status,
)


@dataclass(frozen=True, slots=True)
class CreatorProposalReviewAction:
    """Display-only future review action state."""

    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorProposalReviewRow:
    """Display-only review affordances for one pending proposal."""

    proposal_id: str
    summary: str
    accept_action: CreatorProposalReviewAction
    reject_action: CreatorProposalReviewAction


@dataclass(frozen=True, slots=True)
class CreatorProposalAcceptReadinessModel:
    """Read-only status for future proposal accept/reject affordances."""

    available: bool
    rows: tuple[CreatorProposalReviewRow, ...]
    summary: str
    warnings: tuple[str, ...] = ()


_UNAVAILABLE_SUMMARY = "Proposal review actions unavailable."
_MISSING_PROPOSAL_ID_REASON = "Missing proposal id"


def build_creator_proposal_accept_readiness(
    bridge: object | None,
) -> CreatorProposalAcceptReadinessModel:
    """Build display-only proposal review action readiness from a bridge-like object."""

    status = build_creator_proposal_status(bridge)
    return build_creator_proposal_accept_readiness_from_status(status)


def build_creator_proposal_accept_readiness_from_status(
    status: CreatorProposalStatusModel,
) -> CreatorProposalAcceptReadinessModel:
    """Build display-only proposal review action readiness from proposal status."""

    if not status.available:
        return CreatorProposalAcceptReadinessModel(
            available=False,
            rows=(),
            summary=_UNAVAILABLE_SUMMARY,
            warnings=status.warnings,
        )

    rows = tuple(_build_review_row(row) for row in status.rows)
    if not rows:
        summary = "No proposals waiting for review."
    elif len(rows) == 1:
        summary = "1 proposal can be reviewed."
    else:
        summary = f"{len(rows)} proposals can be reviewed."

    return CreatorProposalAcceptReadinessModel(
        available=True,
        rows=rows,
        summary=summary,
        warnings=status.warnings,
    )


def _build_review_row(row: CreatorProposalListRow) -> CreatorProposalReviewRow:
    proposal_id = str(row.proposal_id or "").strip() or "proposal"
    summary = str(row.summary or "").strip() or "No preview summary"

    if proposal_id == "proposal":
        accept_action = CreatorProposalReviewAction(
            label="Accept",
            enabled=False,
            reason=_MISSING_PROPOSAL_ID_REASON,
        )
        reject_action = CreatorProposalReviewAction(
            label="Reject",
            enabled=False,
            reason=_MISSING_PROPOSAL_ID_REASON,
        )
    else:
        accept_action = CreatorProposalReviewAction(label="Accept", enabled=True)
        reject_action = CreatorProposalReviewAction(label="Reject", enabled=True)

    return CreatorProposalReviewRow(
        proposal_id=proposal_id,
        summary=summary,
        accept_action=accept_action,
        reject_action=reject_action,
    )
