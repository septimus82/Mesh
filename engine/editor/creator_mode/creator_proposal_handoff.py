"""Read-only proposal inbox handoff state for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_proposal_status import CreatorProposalStatusModel

PROPOSAL_OPEN_INBOX_ACTION_ID = "proposal.open_inbox"
_AI_PROPOSALS_TAB = "AI Proposals"


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

    reason = _handoff_unavailable_reason(editor)
    if not reason:
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
        reason=reason,
        pending_count=pending_count,
    )


def _handoff_unavailable_reason(editor: object | None) -> str:
    """Return a concise reason when the official inbox cannot be focused."""

    if editor is None:
        return "Editor unavailable"
    if getattr(editor, "proposal_inbox", None) is None:
        return "AI Proposals inbox unavailable"

    dock = getattr(editor, "dock", None)
    if dock is None:
        return "Right dock unavailable"

    required_methods = (
        "set_right_collapsed",
        "get_right_collapsed",
        "set_right_tab",
        "get_viewport_maximized",
        "toggle_viewport_maximized",
    )
    for method_name in required_methods:
        if not callable(getattr(dock, method_name, None)):
            return "AI Proposals dock controls unavailable"

    try:
        from engine.editor.editor_dock_model import RIGHT_DOCK_TABS  # noqa: PLC0415
    except Exception:  # noqa: BLE001  # REASON: optional UI model import must fail closed
        return "AI Proposals tab unavailable"

    if _AI_PROPOSALS_TAB not in RIGHT_DOCK_TABS:
        return "AI Proposals tab unavailable"

    return ""
