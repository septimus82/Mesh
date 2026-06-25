from __future__ import annotations

import types

from engine.events import MeshEventBus
from engine.game import GameWindow
from tests._typing import as_any


def test_emit_signal_uses_bus_wildcard_as_single_enqueue_path() -> None:
    dummy = types.SimpleNamespace()
    dummy._mesh_event_queue = []
    dummy.last_events = []
    dummy.event_bus = MeshEventBus()

    def _on_any_event(event) -> None:
        dummy._mesh_event_queue.append(event)
        dummy.last_events.append(event.type)
        if len(dummy.last_events) > 10:
            dummy.last_events.pop(0)

    dummy._on_any_event = _on_any_event
    dummy.event_bus.subscribe_all(dummy._on_any_event)

    def _emit_event(event) -> None:
        GameWindow.emit_event(as_any(dummy), event)

    dummy.emit_event = _emit_event

    GameWindow.emit_signal(as_any(dummy), "a", value=1)
    GameWindow.emit_signal(as_any(dummy), "b", value=2)

    q = dummy._mesh_event_queue
    assert [e.type for e in q] == ["a", "b"]
