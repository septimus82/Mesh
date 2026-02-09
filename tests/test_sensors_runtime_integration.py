"""
Integration tests for sensors runtime.
"""
import pytest
from engine.sensors_runtime import SensorRuntime
from engine.sensors_model import SensorEvent
from engine.physics_model import Aabb

def test_sensor_runtime_flow():
    runtime = SensorRuntime()
    scene = {
        "sensors": [
            {"id": "s1", "rect": [0, 0, 100, 100], "enabled": True}  # -50 to 50
        ]
    }
    
    # 1. Entity outside
    # aabb at 200,200 (size 10) -> 195 to 205. No overlap.
    e_aabb = Aabb(200, 200, 10, 10)
    events = runtime.update_entity_sensors(scene, "p1", e_aabb)
    assert events == ()
    assert runtime.last_overlaps_by_entity.get("p1", ()) == ()
    
    # 2. Entity enters
    # aabb at 0,0 (size 10) -> -5 to 5. Overlap.
    e_aabb = Aabb(0, 0, 10, 10)
    events = runtime.update_entity_sensors(scene, "p1", e_aabb)
    assert len(events) == 1
    assert events[0] == SensorEvent("s1", "p1", "enter")
    assert runtime.last_overlaps_by_entity["p1"] == ("s1",)
    
    # 3. Entity stays inside
    events = runtime.update_entity_sensors(scene, "p1", e_aabb)
    assert events == ()
    
    # 4. Entity exits
    e_aabb = Aabb(200, 200, 10, 10)
    events = runtime.update_entity_sensors(scene, "p1", e_aabb)
    assert len(events) == 1
    assert events[0] == SensorEvent("s1", "p1", "exit")
    assert runtime.last_overlaps_by_entity["p1"] == ()

def test_sensor_caching():
    runtime = SensorRuntime()
    scene = {"sensors": [{"id": "test", "rect": [0,0,1,1]}]}
    
    # Should be cached
    res1 = runtime.get_sensors(scene)
    res2 = runtime.get_sensors(scene)
    assert id(res1) == id(res2)
    
    # New dict = new cache entry (even if content is identical, because we cache by id(payload))
    scene2 = {"sensors": [{"id": "test", "rect": [0,0,1,1]}]}
    res3 = runtime.get_sensors(scene2)
    assert id(res1) != id(res3)
    assert res1 == res3 # Value equality

