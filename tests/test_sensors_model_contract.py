"""
Contract tests for the pure sensors model.
"""
import pytest
from engine.sensors_model import (
    SensorDef, SensorEvent, parse_sensors, overlaps_for_entity, diff_overlaps
)
from engine.physics_model import Aabb

def test_parse_sensors_happy_path():
    payload = {
        "sensors": [
            {"id": "b", "rect": [10, 10, 20, 20], "tags": ["t2"], "enabled": True},
            {"id": "a", "rect": [100, 100, 50, 50], "tags": [], "enabled": False},
        ]
    }
    sensors = parse_sensors(payload)
    assert len(sensors) == 2
    
    # Check sorting by ID
    assert sensors[0].id == "a"
    assert sensors[0].tags == ()
    assert sensors[0].enabled is False
    assert sensors[0].aabb == Aabb(100, 100, 50, 50)
    
    assert sensors[1].id == "b"
    assert sensors[1].tags == ("t2",)
    assert sensors[1].aabb == Aabb(10, 10, 20, 20)

def test_parse_sensors_malformed():
    payload = {
        "sensors": [
            {"id": "ok", "rect": [0,0,10,10]},
            {"id": "bad1", "rect": [0,0]}, # not enough coords
            {"rect": [0,0,1,1]}, # missing id
        ]
    }
    sensors = parse_sensors(payload)
    assert len(sensors) == 1
    assert sensors[0].id == "ok"

def test_overlaps_for_entity():
    # Setup
    s1 = SensorDef("s1", Aabb(0, 0, 10, 10)) # Center (0,0), w10, h10. Extents: -5 to 5
    s2 = SensorDef("s2", Aabb(10, 0, 10, 10)) # Center (10,0), w10, h10. Extents: 5 to 15
    s3 = SensorDef("s3", Aabb(100, 0, 10, 10), enabled=False) # Disabled
    
    sensors = (s1, s2, s3)
    
    # Case 1: Inside s1
    e1 = Aabb(0, 0, 2, 2)
    assert overlaps_for_entity(e1, sensors) == ("s1",)
    
    # Case 2: Overlapping s1 and s2 (At x=5)
    e2 = Aabb(5, 0, 2, 2)
    # s1 range x: -5 to 5. s2 range x: 5 to 15.
    # e2 range x: 4 to 6.
    # intersection(s1, e2): max(-5, 4)=4, min(5, 6)=5 -> valid intersection?
    # Aabb intersection: x1 < x2. 4 < 5. Yes.
    assert overlaps_for_entity(e2, sensors) == ("s1", "s2")
    
    # Case 3: Overlapping s3 (disabled)
    e3 = Aabb(100, 0, 2, 2)
    assert overlaps_for_entity(e3, sensors) == ()

def test_diff_overlaps_ordering():
    prev = ("a", "b", "c")
    curr = ("b", "c", "d")
    
    # Exited: a
    # Entered: d
    # Kept: b, c (no event)
    
    events = diff_overlaps("player", prev, curr)
    
    assert len(events) == 2
    assert events[0] == SensorEvent("a", "player", "exit")
    assert events[1] == SensorEvent("d", "player", "enter")

def test_diff_overlaps_multiple():
    prev = ()
    curr = ("x", "y")
    
    events = diff_overlaps("p1", prev, curr)
    assert len(events) == 2
    assert events[0].sensor_id == "x"
    assert events[0].kind == "enter"
    assert events[1].sensor_id == "y"
    assert events[1].kind == "enter"
