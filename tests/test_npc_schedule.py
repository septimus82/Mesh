import pytest

from engine.behaviours.npc_schedule import NpcSchedule
from engine.events import MeshEventBus


class StubDayNight:
    def __init__(self, hour: float):
        self.hour = hour


class StubPatrol:
    def __init__(self):
        self.points = []
        self.current_index = 0
        self._disabled = False
        self.path_id = None
        self.enabled_calls = []
        self.path_calls = []

    def set_enabled(self, value: bool):
        self.enabled_calls.append(value)
        self._disabled = not value

    def set_path_id(self, path_id: str):
        self.path_id = path_id
        self.path_calls.append(path_id)


class StubEntity:
    def __init__(self):
        self.center_x = 0.0
        self.center_y = 0.0
        self.mesh_behaviours_runtime = []


class StubWindow:
    def __init__(self, hour: float):
        self.day_night = StubDayNight(hour)
        self.event_bus = MeshEventBus()
        self.game_state_controller = None


def test_schedule_selects_block_and_moves_entity():
    window = StubWindow(8.0)
    entity = StubEntity()
    schedules = [
        {"start_hour": 6, "end_hour": 12, "mode": "stand", "x": 100, "y": 100},
        {"start_hour": 12, "end_hour": 20, "mode": "stand", "x": 200, "y": 200},
    ]
    sched = NpcSchedule(entity, window, schedules=schedules)
    sched.update(0.016)
    assert entity.center_x == pytest.approx(100.0)
    assert entity.center_y == pytest.approx(100.0)
    window.day_night.hour = 14.0
    sched.update(0.016)
    assert entity.center_x == pytest.approx(200.0)
    assert entity.center_y == pytest.approx(200.0)


def test_wraparound_schedule():
    window = StubWindow(23.0)
    entity = StubEntity()
    schedules = [{"start_hour": 22, "end_hour": 4, "mode": "stand", "x": 300, "y": 300}]
    sched = NpcSchedule(entity, window, schedules=schedules)
    sched.update(0.016)
    assert entity.center_x == pytest.approx(300.0)
    window.day_night.hour = 2.0
    sched.update(0.016)
    assert entity.center_y == pytest.approx(300.0)
    window.day_night.hour = 12.0
    sched.update(0.016)
    # Outside window, no new schedule applied, position unchanged
    assert entity.center_y == pytest.approx(300.0)


def test_patrol_mode_sets_route_and_enables():
    window = StubWindow(10.0)
    entity = StubEntity()
    patrol = StubPatrol()
    entity.mesh_behaviours_runtime = [patrol]
    schedules = [
        {
            "start_hour": 6,
            "end_hour": 20,
            "mode": "patrol",
            "patrol_id": "market_route",
            "patrol_points": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
        }
    ]
    sched = NpcSchedule(entity, window, schedules=schedules)
    sched.update(0.016)
    assert patrol.path_id == "market_route"
    assert patrol.enabled_calls and patrol.enabled_calls[-1] is True
    assert patrol.points == [(1.0, 2.0), (3.0, 4.0)]


def test_enter_event_emitted_on_block_change():
    window = StubWindow(8.0)
    entity = StubEntity()
    received = []

    def on_any(ev):
        received.append(ev.type)

    window.event_bus.subscribe_all(on_any)
    schedules = [
        {"start_hour": 6, "end_hour": 12, "mode": "stand", "enter_event": "morning"},
        {"start_hour": 12, "end_hour": 20, "mode": "stand", "enter_event": "afternoon"},
    ]
    sched = NpcSchedule(entity, window, schedules=schedules)
    sched.update(0.016)
    window.day_night.hour = 14.0
    sched.update(0.016)
    assert "morning" in received
    assert "afternoon" in received
