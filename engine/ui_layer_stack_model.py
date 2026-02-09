"""
Pure model for UI Layer Stack.

Manages overlays, panels, and modals with deterministic input routing and draw order.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Tuple, Optional, List

@dataclass(frozen=True)
class UiLayer:
    """A single UI layer definition."""
    id: str
    kind: str  # "panel", "overlay", "modal"
    visible: bool = False
    z: int = 0
    blocks_input: bool = False

@dataclass(frozen=True)
class UiStackState:
    """Immutable state of the UI stack."""
    layers: Tuple[UiLayer, ...] = field(default_factory=tuple)
    active_modal_id: Optional[str] = None

def normalize_layers(layers: Tuple[UiLayer, ...]) -> Tuple[UiLayer, ...]:
    """Sort layers by Z (ascending) then ID (for stability)."""
    return tuple(sorted(layers, key=lambda l: (l.z, l.id)))

def compute_active_modal(layers: Tuple[UiLayer, ...]) -> Optional[str]:
    """Find the topmost visible modal."""
    # Filter for visible modals
    modals = [l for l in layers if l.visible and l.kind == "modal"]
    if not modals:
        return None
    # Sort by Z desc (top first)
    modals.sort(key=lambda l: l.z, reverse=True)
    return modals[0].id

def get_layer(state: UiStackState, layer_id: str) -> Optional[UiLayer]:
    for l in state.layers:
        if l.id == layer_id:
            return l
    return None

def update_layer(state: UiStackState, layer_id: str, **updates) -> UiStackState:
    """Return new state with updated layer properties."""
    new_layers = []
    found = False
    for l in state.layers:
        if l.id == layer_id:
            found = True
            # Create updated copy
            new_layers.append(replace(l, **updates))
        else:
            new_layers.append(l)
    
    if not found:
        return state

    norm_layers = normalize_layers(tuple(new_layers))
    return UiStackState(
        layers=norm_layers,
        active_modal_id=compute_active_modal(norm_layers)
    )

def register_layer(state: UiStackState, layer: UiLayer) -> UiStackState:
    """Add a new layer if ID not exists."""
    for l in state.layers:
        if l.id == layer.id:
            return state
    
    new_layers = state.layers + (layer,)
    norm_layers = normalize_layers(new_layers)
    return UiStackState(
        layers=norm_layers,
        active_modal_id=compute_active_modal(norm_layers)
    )

def set_visible(state: UiStackState, layer_id: str, visible: bool) -> UiStackState:
    return update_layer(state, layer_id, visible=visible)

def push_modal(state: UiStackState, modal_id: str) -> UiStackState:
    """Make a modal visible."""
    # Ensure it is registered as a modal? We assume it is.
    # Just set visible=True.
    layer = get_layer(state, modal_id)
    if not layer:
        return state
    if layer.kind != "modal":
        # Maybe allow forcing it? For now strict.
        pass
        
    return set_visible(state, modal_id, True)

def pop_modal(state: UiStackState, modal_id: str) -> UiStackState:
    """Hide a modal."""
    return set_visible(state, modal_id, False)

def route_input_targets(state: UiStackState) -> Tuple[str, ...]:
    """
    Return list of layer IDs that should receive input, in priority order.
    
    Priority:
    1. Active Modal (if blocking) - creates a barrier?
       If active modal blocks input, NOTHING else gets input?
       Or just it is first?
       "Routes input in priority order: 1) active modal... 2) focused widget..."
       If blocks_input is True, it implies exclusive capture.
    """
    targets = []
    
    if state.active_modal_id:
        modal = get_layer(state, state.active_modal_id)
        if modal:
            targets.append(modal.id)
            if modal.blocks_input:
                return tuple(targets) # Barrier
    
    # If no blocking modal, others can receive input?
    # User constraint: "Routes input in priority order ... 2) focused widget"
    # This function returns LAYER targets. Focused widget is separate (handled by caller fallback).
    # Does this return other visible panels?
    # "then other visible layers by z desc"
    
    # We already added active modal. Now add others.
    # Sort visible layers by Z desc
    sorted_layers = sorted([l for l in state.layers if l.visible], key=lambda x: x.z, reverse=True)
    
    for l in sorted_layers:
        if l.id == state.active_modal_id:
            continue # Already added
        targets.append(l.id)
        
    return tuple(targets)
