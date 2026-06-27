from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DockTabSpec:
    name: str
    tooltip: str


LEFT_DOCK_TAB_SPECS: tuple[DockTabSpec, ...] = (
    DockTabSpec("Project", "Project Explorer -- Files in the project"),
    DockTabSpec("Scene", "Scene Browser -- Search + open scenes"),
    DockTabSpec("Outliner", "Outliner -- Entities in the scene"),
)
# Right dock order: Inspector Assets Items Prefabs Quests Dialogue AI Chat AI Proposals History Problems Debug.
RIGHT_DOCK_TAB_SPECS: tuple[DockTabSpec, ...] = (
    DockTabSpec("Inspector", "Inspector -- Edit selected entity"),
    DockTabSpec("Assets", "Assets -- Search + spawn assets"),
    DockTabSpec("Items", "Items -- Edit item definitions"),
    DockTabSpec("Prefabs", "Prefabs -- Edit prefab definitions"),
    DockTabSpec("Quests", "Quests -- Edit quest definitions"),
    DockTabSpec("Dialogue", "Dialogue -- Browse dialogue database"),
    DockTabSpec("AI Chat", "AI Chat -- Ask Claude to stage scene proposals"),
    DockTabSpec("AI Proposals", "AI Proposals -- Review staged AI changes"),
    DockTabSpec("History", "History -- Undo/redo stack"),
    DockTabSpec("Problems", "Problems -- Scan + fix common issues"),
    DockTabSpec("Debug", "Debug -- Quests, cutscenes, events"),
)
LEFT_DOCK_TABS: tuple[str, ...] = tuple(spec.name for spec in LEFT_DOCK_TAB_SPECS)
RIGHT_DOCK_TABS: tuple[str, ...] = tuple(spec.name for spec in RIGHT_DOCK_TAB_SPECS)
DOCK_TAB_TOOLTIPS: dict[str, str] = {
    spec.name: spec.tooltip for spec in (*LEFT_DOCK_TAB_SPECS, *RIGHT_DOCK_TAB_SPECS)
}
