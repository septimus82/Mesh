"""Read-only proposal inbox handoff state for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_proposal_status import CreatorProposalStatusModel

PROPOSAL_OPEN_INBOX_ACTION_ID = "proposal.open_inbox"


@dataclass(frozen=True, slots=True)
class CreatorProposalHandoffModel:
    """Display-only handoff toward the official AI Proposals inbox."""

    available: bool
    enabled: bool
    label: str
    reason: str = ""
    pending_count: int = 0
    action_id: str = ""


def build_creator_proposal_handoff(
    editor: object | None,
    proposal_status: CreatorProposalStatusModel,
) -> CreatorProposalHandoffModel:
    """Build read-only handoff state without calling inbox or bridge methods."""

    pending_count = int(proposal_status.pending_count or 0)

    if not proposal_status.available:
        return CreatorProposalHandoffModel(
            available=False,
            enabled=False,
            label="Proposal review unavailable",
            reason="Proposal status unavailable",
            pending_count=pending_count,
        )

    if pending_count <= 0:
        return CreatorProposalHandoffModel(
            available=False,
            enabled=False,
            label="No proposals to review",
            reason="",
            pending_count=0,
        )

    if editor is not None and getattr(editor, "proposal_inbox", None) is not None:
        return CreatorProposalHandoffModel(
            available=True,
            enabled=True,
            label="Review in AI Proposals",
            reason="",
            pending_count=pending_count,
            action_id=PROPOSAL_OPEN_INBOX_ACTION_ID,
        )

    return CreatorProposalHandoffModel(
        available=False,
        enabled=False,
        label="Review in AI Proposals",
        reason="AI Proposals inbox unavailable",
        pending_count=pending_count,
    )
