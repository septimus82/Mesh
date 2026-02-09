"""
Contract tests for behaviour event routing model.
"""
from engine.behaviour_event_router_model import (
    BehaviourEvent,
    DispatchPlan,
    build_sensor_behaviour_events,
    compute_dispatch_targets,
    handler_name_for_event,
    should_fallback_to_primary,
)
from engine.sensors_model import SensorEvent, SensorDef
from engine.physics_model import Aabb

def test_handler_name_mapping():
    assert handler_name_for_event("sensor_enter") == "on_sensor_enter"
    assert handler_name_for_event("sensor_exit") == "on_sensor_exit"
    assert handler_name_for_event("custom") == "on_custom"

def test_build_behaviour_events():
    s_events = (
        SensorEvent("s1", "e1", "enter"),
        SensorEvent("s2", "e1", "exit"),
    )
    
    s_defs = (
        SensorDef("s1", Aabb(0,0,0,0), tags=("trap", "zone")),
        SensorDef("s2", Aabb(0,0,0,0), tags=()),
    )
    
    b_events = build_sensor_behaviour_events(s_events, s_defs, "scene1.json")
    
    assert len(b_events) == 2
    
    # Check enrichment
    e1 = b_events[0]
    assert e1.kind == "sensor_enter"
    assert e1.entity_id == "e1"
    assert e1.sensor_id == "s1"
    assert e1.tags == ("trap", "zone")
    assert e1.scene_path == "scene1.json"
    assert e1.origin == "unknown"

def test_compute_dispatch_targets_priority():
    event = BehaviourEvent("sensor_enter", "player", "s1")
    
    # Case 1: Both handle it
    e_idx = {"player": ("on_sensor_enter",)}
    s_idx = ("on_sensor_enter",)
    
    plan = compute_dispatch_targets(event, e_idx, s_idx, resolved_entity_id="player")
    assert isinstance(plan, DispatchPlan)
    assert plan.entity_handler_enabled is True
    assert plan.scene_target_enabled is True
    assert plan.resolved_entity_target_id == "player"
    
    # Case 2: Only entity
    e_idx = {"player": ("on_sensor_enter",)}
    s_idx = ()
    plan = compute_dispatch_targets(event, e_idx, s_idx, resolved_entity_id="player")
    assert plan.entity_handler_enabled is True
    assert plan.scene_target_enabled is False

    # Case 3: Only scene
    e_idx = {}
    s_idx = ("on_sensor_enter",)
    plan = compute_dispatch_targets(event, e_idx, s_idx, resolved_entity_id=None)
    assert plan.entity_handler_enabled is False
    assert plan.scene_target_enabled is True

def test_fallback_policy():
    event = BehaviourEvent("sensor_enter", "p1", "s1", tags=("primary_player",))
    assert should_fallback_to_primary(event) is True
    event = BehaviourEvent("sensor_enter", "p1", "s1", origin="player")
    assert should_fallback_to_primary(event) is True
    event = BehaviourEvent("sensor_enter", "p1", "s1")
    assert should_fallback_to_primary(event) is False

def test_dispatch_plan_flags_fallback():
    event = BehaviourEvent("sensor_enter", "p1", "s1", origin="player")
    plan = compute_dispatch_targets(event, {}, ("on_sensor_enter",), resolved_entity_id=None)
    assert plan.allow_primary_fallback is True
    assert plan.scene_target_enabled is True
