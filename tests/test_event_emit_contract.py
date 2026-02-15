from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from engine.event_emit import emit_gameplay_event
from engine.gameplay_event_bus import GameplayEventBus


class _LegacyBus:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        captured = dict(payload)
        self.calls.append((event_type, captured))
        return {"event_type": event_type, "payload": captured}


def test_emit_gameplay_event_prefers_gameplay_bus_when_present() -> None:
    gameplay_bus = GameplayEventBus()
    legacy_bus = _LegacyBus()
    ctx = SimpleNamespace(gameplay_event_bus=gameplay_bus, event_bus=legacy_bus)

    payload = {"foo": "bar", "value": 3}
    emit_gameplay_event(
        ctx,
        "test_event",
        payload,
        source_entity_id="entity_1",
        source_behaviour="ContractTest",
    )

    pending = gameplay_bus.peek()
    assert len(pending) == 1
    assert pending[0].event_type == "test_event"
    assert pending[0].payload == payload
    assert pending[0].source_entity == "entity_1"
    assert pending[0].source_behaviour == "ContractTest"
    assert legacy_bus.calls == []


def test_emit_gameplay_event_falls_back_to_legacy_event_bus() -> None:
    legacy_bus = _LegacyBus()
    ctx = SimpleNamespace(event_bus=legacy_bus)

    payload = {"alpha": 1}
    emit_gameplay_event(ctx, "legacy_event", payload, source_entity_id="ignored")

    assert legacy_bus.calls == [("legacy_event", {"alpha": 1})]


def test_emit_gameplay_event_payload_is_not_mutated() -> None:
    gameplay_bus = GameplayEventBus()
    payload = {"nested": {"x": 1}, "list": [1, 2, 3]}
    snapshot = {"nested": {"x": 1}, "list": [1, 2, 3]}

    emit_gameplay_event(
        gameplay_bus,
        "payload_event",
        payload,
        source_entity_id="source_entity",
        source_behaviour="PayloadContract",
    )

    assert payload == snapshot
    pending = gameplay_bus.peek()
    assert len(pending) == 1
    assert pending[0].payload == snapshot
