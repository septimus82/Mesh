"""State containers for the read-only Creator Mode shell."""

from __future__ import annotations

from dataclasses import dataclass, field

from .creator_inspector import CreatorInspectorModel, empty_creator_inspector
from .creator_door_panel import CreatorDoorPanelModel
from .creator_proposal_accept_readiness import (
    CreatorProposalAcceptReadinessModel,
    build_creator_proposal_accept_readiness,
)
from .creator_proposal_review_details import (
    CreatorProposalReviewDetailsModel,
    build_creator_proposal_review_details,
)
from .creator_proposal_status import CreatorProposalStatusModel, unavailable_creator_proposal_status

TOP_ACTIONS: tuple[str, ...] = ("Save", "Test Play", "Fix Problems", "Advanced Mode")
LEFT_TOOLS: tuple[str, ...] = (
    "Map",
    "Person",
    "Door",
    "Monster Area",
    "Battle",
    "Quest",
    "Item",
    "Light",
)
BOTTOM_PANEL_TITLE = "Things to Fix"


@dataclass(frozen=True, slots=True)
class CreatorModeSnapshot:
    """Read-only data needed to render the Creator Mode shell."""

    active: bool = False
    selected_kind: str = "Thing"
    selected_title: str = ""
    selected_summary: str = ""
    inspector: CreatorInspectorModel = field(default_factory=empty_creator_inspector)
    door_panel: CreatorDoorPanelModel | None = None
    proposal_status: CreatorProposalStatusModel = field(
        default_factory=unavailable_creator_proposal_status
    )
    proposal_accept_readiness: CreatorProposalAcceptReadinessModel = field(
        default_factory=lambda: build_creator_proposal_accept_readiness(None)
    )
    proposal_review_details: CreatorProposalReviewDetailsModel = field(
        default_factory=lambda: build_creator_proposal_review_details(None)
    )
    last_action_message: str = ""
    last_action_ok: bool | None = None
    top_actions: tuple[str, ...] = TOP_ACTIONS
    left_tools: tuple[str, ...] = LEFT_TOOLS
    bottom_panel_title: str = BOTTOM_PANEL_TITLE
