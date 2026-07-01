"""Pure overlay view models for Creator Mode."""

from __future__ import annotations

from dataclasses import dataclass

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
    )
