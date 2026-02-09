"""
Contract tests for UI Layer Stack Model.
"""
from engine.ui_layer_stack_model import (
    UiLayer, UiStackState, normalize_layers, compute_active_modal,
    register_layer, set_visible, route_input_targets, push_modal, pop_modal
)

def test_normalize_ordering():
    l1 = UiLayer("a", "panel", z=10)
    l2 = UiLayer("b", "overlay", z=5)
    l3 = UiLayer("c", "modal", z=10)
    
    # Sort by Z asc, then ID
    # Expected: b(5), a(10), c(10)
    layers = normalize_layers((l3, l2, l1))
    assert layers[0].id == "b"
    assert layers[1].id == "a"
    assert layers[2].id == "c"

def test_active_modal():
    l1 = UiLayer("m1", "modal", visible=True, z=100)
    l2 = UiLayer("m2", "modal", visible=False, z=200) # invisible
    l3 = UiLayer("m3", "modal", visible=True, z=50)   # lower z
    
    state = UiStackState(layers=(l1, l2, l3))
    # compute active: m1 is topmost visible. m2 is invisible. m3 is lower.
    active = compute_active_modal(state.layers)
    assert active == "m1"

def test_state_mutations():
    state = UiStackState()
    l1 = UiLayer("m1", "modal", visible=False, z=100)
    
    state = register_layer(state, l1)
    assert len(state.layers) == 1
    assert state.active_modal_id is None
    
    state = push_modal(state, "m1")
    assert state.layers[0].visible is True
    assert state.active_modal_id == "m1"
    
    state = pop_modal(state, "m1")
    assert state.layers[0].visible is False
    assert state.active_modal_id is None

def test_input_routing_blocking():
    state = UiStackState()
    l1 = UiLayer("bg", "panel", visible=True, z=0)
    l2 = UiLayer("m1", "modal", visible=True, z=100, blocks_input=True)
    
    state = register_layer(state, l1)
    state = register_layer(state, l2)
    # active modal is m1
    
    targets = route_input_targets(state)
    # m1 blocks, so only m1
    assert targets == ("m1",)

def test_input_routing_non_blocking():
    state = UiStackState()
    l1 = UiLayer("bg", "panel", visible=True, z=0)
    l2 = UiLayer("overlay", "overlay", visible=True, z=10)
    
    state = register_layer(state, l1)
    state = register_layer(state, l2)
    
    # Sorted by Z desc: overlay(10), bg(0)
    targets = route_input_targets(state)
    assert targets == ("overlay", "bg")
