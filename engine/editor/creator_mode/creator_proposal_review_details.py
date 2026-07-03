"""Read-only proposal review detail models for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_proposal_status import CreatorProposalStatusModel, build_creator_proposal_status


@dataclass(frozen=True, slots=True)
class CreatorProposalReviewDetail:
    """Sanitized detail for one pending proposal."""

    proposal_id: str
    summary: str
    affected_ids: tuple[str, ...]
    dry_run_ok: bool | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CreatorProposalReviewDetailsModel:
    """Read-only proposal review details prepared for future UI."""

    available: bool
    details: tuple[CreatorProposalReviewDetail, ...]
    summary: str
    warnings: tuple[str, ...] = ()


_UNAVAILABLE_SUMMARY = "Proposal review details unavailable."


def build_creator_proposal_review_details(
    bridge: object | None,
) -> CreatorProposalReviewDetailsModel:
    """Build read-only proposal review details from a bridge-like object."""

    status = build_creator_proposal_status(bridge)
    return build_creator_proposal_review_details_from_status(status)


def build_creator_proposal_review_details_from_status(
    status: CreatorProposalStatusModel,
) -> CreatorProposalReviewDetailsModel:
    """Build read-only proposal review details from an existing status model."""

    if not status.available:
        return CreatorProposalReviewDetailsModel(
            available=False,
            details=(),
            summary=_UNAVAILABLE_SUMMARY,
            warnings=status.warnings,
        )

    details = tuple(
        CreatorProposalReviewDetail(
            proposal_id=row.proposal_id,
            summary=row.summary,
            affected_ids=row.affected_ids,
            dry_run_ok=row.dry_run_ok,
            warnings=row.dry_run_warnings,
            errors=row.dry_run_errors,
        )
        for row in status.rows
    )
    if not details:
        summary = "No proposal details to show."
    elif len(details) == 1:
        summary = "1 proposal detail ready."
    else:
        summary = f"{len(details)} proposal details ready."

    return CreatorProposalReviewDetailsModel(
        available=True,
        details=details,
        summary=summary,
        warnings=status.warnings,
    )
