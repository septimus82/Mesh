"""Read-only staged proposal status for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreatorProposalListRow:
    """One read-only pending proposal row for Creator Mode."""

    proposal_id: str
    summary: str
    affected_count: int = 0


@dataclass(frozen=True, slots=True)
class CreatorProposalStatusModel:
    """Read-only summary of proposals waiting for human review."""

    available: bool
    pending_count: int
    summary: str
    rows: tuple[CreatorProposalListRow, ...] = ()
    warnings: tuple[str, ...] = ()


_UNAVAILABLE_SUMMARY = "Proposal review status unavailable."


def unavailable_creator_proposal_status(
    *,
    warnings: tuple[str, ...] = (),
) -> CreatorProposalStatusModel:
    return CreatorProposalStatusModel(
        available=False,
        pending_count=0,
        summary=_UNAVAILABLE_SUMMARY,
        rows=(),
        warnings=warnings,
    )


def build_creator_proposal_status(bridge: object | None) -> CreatorProposalStatusModel:
    """Build a fail-closed read-only proposal status from a bridge-like object."""

    if bridge is None:
        return unavailable_creator_proposal_status()

    list_fn = getattr(bridge, "list_pending_proposals", None)
    if not callable(list_fn):
        return unavailable_creator_proposal_status()

    try:
        pending = list_fn()
    except Exception as exc:  # noqa: BLE001
        return unavailable_creator_proposal_status(
            warnings=(f"Could not read pending proposals: {exc}",),
        )

    if not isinstance(pending, list):
        return unavailable_creator_proposal_status(
            warnings=("Pending proposal list was malformed.",),
        )

    rows = tuple(_sanitize_pending_row(row) for row in pending)
    count = len(rows)
    if count == 0:
        summary = "No staged proposals."
    elif count == 1:
        summary = "1 proposal waiting for review"
    else:
        summary = f"{count} proposals waiting for review"

    return CreatorProposalStatusModel(
        available=True,
        pending_count=count,
        summary=summary,
        rows=rows,
        warnings=(),
    )


def _sanitize_pending_row(row: object) -> CreatorProposalListRow:
    if not isinstance(row, dict):
        return CreatorProposalListRow(
            proposal_id="proposal",
            summary="No preview summary",
            affected_count=0,
        )

    proposal_id = str(row.get("proposal_id") or "proposal").strip() or "proposal"
    summary = str(row.get("preview_summary") or "No preview summary").strip() or "No preview summary"
    affected_ids = row.get("affected_ids")
    affected_count = len(affected_ids) if isinstance(affected_ids, list) else 0
    return CreatorProposalListRow(
        proposal_id=proposal_id,
        summary=summary,
        affected_count=affected_count,
    )
