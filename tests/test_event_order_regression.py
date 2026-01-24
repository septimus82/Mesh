from __future__ import annotations

import types

from engine.events import MeshEventBus
from engine.game import GameWindow


def test_emit_signal_enqueues_event_before_bus_wildcard_enqueue() -> None:
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
        GameWindow.emit_event(dummy, event)  # type: ignore[arg-type]

    dummy.emit_event = _emit_event

    GameWindow.emit_signal(dummy, "a", value=1)  # type: ignore[arg-type]
    GameWindow.emit_signal(dummy, "b", value=2)  # type: ignore[arg-type]

    q = dummy._mesh_event_queue
    assert [e.type for e in q] == ["a", "a", "b", "b"]
    assert q[0] is q[1]
    assert q[2] is q[3]

