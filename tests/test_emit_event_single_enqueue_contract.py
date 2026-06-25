from __future__ import annotations

from types import SimpleNamespace

from engine.events import MeshEvent, MeshEventBus
from engine.game import GameWindow
from tests._typing import as_any


def _window_with_bus() -> SimpleNamespace:
    window = SimpleNamespace(_mesh_event_queue=[], last_events=[], event_bus=MeshEventBus())
    window.event_bus.subscribe_all(lambda event: GameWindow._on_any_event(as_any(window), event))
    return window


def test_emit_event_enqueues_once_through_bus_wildcard() -> None:
    window = _window_with_bus()
    event = MeshEvent("emit_path", {"value": 1})

    GameWindow.emit_event(as_any(window), event)

    assert window._mesh_event_queue == [event]
    assert window.last_events == ["emit_path"]


def test_direct_bus_emit_event_still_enqueues_once() -> None:
    window = _window_with_bus()
    event = MeshEvent("direct_bus_path", {"value": 2})

    window.event_bus.emit_event(event)

    assert window._mesh_event_queue == [event]
    assert window.last_events == ["direct_bus_path"]


def test_direct_bus_emit_still_enqueues_once() -> None:
    window = _window_with_bus()

    window.event_bus.emit("direct_bus_emit", value=3)

    assert len(window._mesh_event_queue) == 1
    assert window._mesh_event_queue[0].type == "direct_bus_emit"
    assert window._mesh_event_queue[0].payload == {"value": 3}
    assert window.last_events == ["direct_bus_emit"]


def test_emit_event_without_bus_enqueues_once() -> None:
    window = SimpleNamespace(_mesh_event_queue=[], last_events=[], event_bus=None)
    event = MeshEvent("no_bus_path", {"value": 4})

    GameWindow.emit_event(as_any(window), event)

    assert window._mesh_event_queue == [event]
    assert window.last_events == []


def test_emit_event_with_bus_error_falls_back_to_single_enqueue() -> None:
    class BrokenBus:
        def emit_event(self, _event: MeshEvent) -> None:
            raise RuntimeError("bus unavailable")

    window = SimpleNamespace(_mesh_event_queue=[], last_events=[], event_bus=BrokenBus())
    event = MeshEvent("bus_error_path", {"value": 5})

    GameWindow.emit_event(as_any(window), event)

    assert window._mesh_event_queue == [event]
    assert window.last_events == []
