"""Read-only staged proposal status for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreatorProposalStatusModel:
    """Read-only summary of proposals waiting for human review."""

    available: bool
    pending_count: int
    summary: str
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

    count = len(pending)
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
        warnings=(),
    )
