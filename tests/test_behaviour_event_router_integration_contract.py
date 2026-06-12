"""
Integration contract for behaviour event router runtime.
"""

from engine.behaviour_event_router import dispatch_events
from engine.behaviour_event_router_model import BehaviourEvent


class MockBehaviour:
    def __init__(self):
        self.calls = []

    def on_sensor_enter(self, sensor_id):
        self.calls.append(f"enter:{sensor_id}")

    def on_sensor_exit(self, sensor_id):
        self.calls.append(f"exit:{sensor_id}")

    def on_crash(self, sensor_id):
        raise ValueError("Boom")

class MockEntity:
    def __init__(self, eid):
        self.eid = eid
        self.mesh_behaviours_runtime = []

class MockSceneIndex:
    def __init__(self):
        self.lookup = {}

class MockSceneController:
    def __init__(self):
        self._scene_index = MockSceneIndex()
        self.calls = []
        self.entities = None

    def on_sensor_enter(self, entity_id, sensor_id):
        self.calls.append(f"scene_enter:{entity_id}:{sensor_id}")

def test_dispatch_flow_success():
    # Setup
    scene = MockSceneController()
    entity = MockEntity("p1")
    beh = MockBehaviour()
    entity.mesh_behaviours_runtime.append(beh)

    scene._scene_index.lookup["p1"] = entity

    # Events
    events = (
        BehaviourEvent("sensor_enter", "p1", "zone_a"),
    )

    # Execute
    dispatch_events(scene, events)

    # Verify entity called
    assert len(beh.calls) == 1
    assert beh.calls[0] == "enter:zone_a"

    # Verify scene called (multicast)
    assert len(scene.calls) == 1
    assert scene.calls[0] == "scene_enter:p1:zone_a"

def test_dispatch_exception_safety(caplog):
    scene = MockSceneController()
    entity = MockEntity("p1")
    beh = MockBehaviour()
    # Replace handler with crashing one
    beh.on_sensor_enter = beh.on_crash
    entity.mesh_behaviours_runtime.append(beh)
    scene._scene_index.lookup["p1"] = entity

    events = (
        BehaviourEvent("sensor_enter", "p1", "zone_a"),
    )

    # Should not raise
    dispatch_events(scene, events)

    # Should log error
    assert "Error dispatching" in caplog.text

def test_dispatch_missing_entity():
    scene = MockSceneController()
    # No p1 in index

    events = (BehaviourEvent("sensor_enter", "p1", "zone_a"),)

    dispatch_events(scene, events)

    # Should still call scene if scene handles it
    assert len(scene.calls) == 1
    assert scene.calls[0] == "scene_enter:p1:zone_a"

def test_dispatch_fallback_to_primary_player(caplog):
    import logging

    from engine.behaviour_event_router import _UNRESOLVED_WARNED
    _UNRESOLVED_WARNED.clear()  # Clear the dedup cache before test
    caplog.set_level(logging.WARNING, logger="engine.behaviour_event_router")

    scene = MockSceneController()
    # Provide a primary player entity fallback
    primary = MockEntity("player")
    beh = MockBehaviour()
    primary.mesh_behaviours_runtime.append(beh)
    # Use entity store fallback
    class MockEntities:
        def find_primary_player_sprite(self, _controller):
            return primary
    scene.entities = MockEntities()

    events = (BehaviourEvent("sensor_enter", "missing", "zone_a", origin="player"),)
    dispatch_events(scene, events)
    assert beh.calls == ["enter:zone_a"]
    assert scene.calls == ["scene_enter:missing:zone_a"]
    # No warning expected when fallback succeeds - the primary player was found

def test_dispatch_warning_dedup(caplog):
    import logging
    caplog.set_level(logging.WARNING, logger="engine.behaviour_event_router")

    scene = MockSceneController()
    events = (
        BehaviourEvent("sensor_enter", "missing", "zone_a"),
        BehaviourEvent("sensor_enter", "missing", "zone_b"),
    )
    dispatch_events(scene, events)
    assert caplog.text.count("Unresolved entity_id=missing") == 1
