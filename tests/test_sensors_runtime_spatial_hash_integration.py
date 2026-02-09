from __future__ import annotations

from engine.physics_model import Aabb
from engine.sensors_model import parse_sensors, overlaps_for_entity, diff_overlaps
from engine.sensors_runtime import SensorRuntime


def _scene_with_sensors() -> dict:
    return {
        "sensors": [
            {"id": "s1", "rect": [0, 0, 10, 10], "tags": ["a"], "enabled": True},
            {"id": "s2", "rect": [20, 0, 10, 10], "tags": ["b"], "enabled": True},
            {"id": "s3", "rect": [0, 20, 10, 10], "tags": ["c"], "enabled": True},
        ]
    }


def test_sensor_events_match_baseline() -> None:
    scene = _scene_with_sensors()
    sensors = parse_sensors(scene)
    runtime = SensorRuntime(cell_size_px=10)

    entity_id = "e1"
    aabb = Aabb(0, 0, 5, 5)
    expected_overlaps = overlaps_for_entity(aabb, sensors)
    expected_events = diff_overlaps(entity_id, (), expected_overlaps)

    events = runtime.update_entity_sensors(scene, entity_id, aabb)
    assert events == expected_events

    # Move to another sensor
    aabb2 = Aabb(20, 0, 5, 5)
    expected_overlaps2 = overlaps_for_entity(aabb2, sensors)
    expected_events2 = diff_overlaps(entity_id, expected_overlaps, expected_overlaps2)
    events2 = runtime.update_entity_sensors(scene, entity_id, aabb2)
    assert events2 == expected_events2


def test_perf_counters_deterministic() -> None:
    scene = _scene_with_sensors()
    runtime = SensorRuntime(cell_size_px=10)
    runtime.enable_perf_counters(True)
    runtime.update_entity_sensors(scene, "e1", Aabb(0, 0, 5, 5))
    runtime.update_entity_sensors(scene, "e2", Aabb(20, 0, 5, 5))
    assert runtime.candidate_count == 2
    assert runtime.exact_checks_count == 2
