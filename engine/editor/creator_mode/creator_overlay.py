"""Pure overlay view models for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_door_panel import CreatorDoorPanelModel
from .creator_entity_move_panel import CreatorEntityMovePanelModel
from .creator_entity_rename_panel import CreatorEntityRenamePanelModel
from .creator_proposal_accept_readiness import CreatorProposalAcceptReadinessModel
from .creator_proposal_handoff import CreatorProposalHandoffModel
from .creator_proposal_review_details import CreatorProposalReviewDetailsModel
from .creator_proposal_status import CreatorProposalStatusModel
from .creator_state import CreatorModeSnapshot


@dataclass(frozen=True, slots=True)
class CreatorOverlayLine:
    """One prepared line for a future Creator Mode overlay renderer."""

    text: str
    region: str


@dataclass(frozen=True, slots=True)
class CreatorOverlayModel:
    """Read-only, renderer-neutral Creator Mode overlay data."""

    active: bool
    title: str
    top_actions: tuple[str, ...]
    left_tools: tuple[str, ...]
    selected_title: str
    selected_kind: str
    selected_summary: str
    inspector_fields: tuple[tuple[str, str, bool], ...]
    warnings: tuple[str, ...]
    bottom_title: str
    proposal_status: CreatorProposalStatusModel
    proposal_accept_readiness: CreatorProposalAcceptReadinessModel
    proposal_review_details: CreatorProposalReviewDetailsModel
    proposal_handoff: CreatorProposalHandoffModel
    movement_panel: CreatorEntityMovePanelModel | None = None
    rename_panel: CreatorEntityRenamePanelModel | None = None
    door_panel: CreatorDoorPanelModel | None = None
    last_action_message: str = ""
    last_action_ok: bool | None = None


def build_creator_overlay_model(snapshot: CreatorModeSnapshot) -> CreatorOverlayModel:
    """Build a renderer-neutral Creator Mode overlay model."""

    inspector = snapshot.inspector
    return CreatorOverlayModel(
        active=bool(snapshot.active),
        title="Creator Mode",
        top_actions=tuple(snapshot.top_actions),
        left_tools=tuple(snapshot.left_tools),
        selected_title=str(snapshot.selected_title or inspector.title or ""),
        selected_kind=str(snapshot.selected_kind or inspector.kind or "Thing"),
        selected_summary=str(snapshot.selected_summary or inspector.summary or ""),
        inspector_fields=tuple(
            (field.label, field.value, field.missing)
            for field in inspector.fields
        ),
        warnings=tuple(inspector.warnings),
        bottom_title=str(snapshot.bottom_panel_title or "Things to Fix"),
        proposal_status=snapshot.proposal_status,
        proposal_accept_readiness=snapshot.proposal_accept_readiness,
        proposal_review_details=snapshot.proposal_review_details,
        proposal_handoff=snapshot.proposal_handoff,
        movement_panel=snapshot.movement_panel,
        rename_panel=snapshot.rename_panel,
        door_panel=snapshot.door_panel,
        last_action_message=str(snapshot.last_action_message or ""),
        last_action_ok=snapshot.last_action_ok,
    )
