"""State containers for the read-only Creator Mode shell."""

from __future__ import annotations

from dataclasses import dataclass, field

from .creator_inspector import CreatorInspectorModel, empty_creator_inspector

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
    top_actions: tuple[str, ...] = TOP_ACTIONS
    left_tools: tuple[str, ...] = LEFT_TOOLS
    bottom_panel_title: str = BOTTOM_PANEL_TITLE
