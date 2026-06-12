
from engine.behaviours.time_of_day_gate import TimeOfDayGate
from engine.events import MeshEventBus


class StubDayNight:
    def __init__(self, hour: float):
        self.hour = hour


class StubWindow:
    def __init__(self, hour: float):
        self.day_night = StubDayNight(hour)
        self.event_bus = MeshEventBus()
        self.game_state_controller = None


class StubEntity:
    def __init__(self):
        self.visible = True
        self.mesh_name = "stub"


def test_gate_active_during_day():
    window = StubWindow(10.0)
    entity = StubEntity()
    gate = TimeOfDayGate(entity, window, start_hour=6.0, end_hour=18.0, invert=False, affect_visibility=True)
    gate.update(0.016)
    assert entity.visible is True


def test_gate_inactive_at_night():
    window = StubWindow(2.0)
    entity = StubEntity()
    gate = TimeOfDayGate(entity, window, start_hour=6.0, end_hour=18.0, invert=False, affect_visibility=True)
    gate.update(0.016)
    assert entity.visible is False


def test_gate_wrap_window():
    window = StubWindow(23.0)
    entity = StubEntity()
    gate = TimeOfDayGate(entity, window, start_hour=22.0, end_hour=4.0, invert=False, affect_visibility=True)
    gate.update(0.016)
    assert entity.visible is True
    window.day_night.hour = 3.0
    gate.update(0.016)
    assert entity.visible is True
    window.day_night.hour = 12.0
    gate.update(0.016)
    assert entity.visible is False


def test_gate_invert_flag():
    window = StubWindow(10.0)
    entity = StubEntity()
    gate = TimeOfDayGate(entity, window, start_hour=6.0, end_hour=18.0, invert=True, affect_visibility=True)
    gate.update(0.016)
    assert entity.visible is False
    window.day_night.hour = 2.0
    gate.update(0.016)
    assert entity.visible is True


def test_gate_emits_events_on_change():
    window = StubWindow(2.0)
    entity = StubEntity()
    received = []

    def on_any(event):
        received.append(event.type)

    window.event_bus.subscribe_all(on_any)
    gate = TimeOfDayGate(
        entity,
        window,
        start_hour=6.0,
        end_hour=18.0,
        open_event="opened",
        close_event="closed",
    )
    gate.update(0.016)  # inactive initially
    window.day_night.hour = 8.0
    gate.update(0.016)  # becomes active -> opened
    window.day_night.hour = 22.0
    gate.update(0.016)  # becomes inactive -> closed
    assert "opened" in received
    assert "closed" in received
