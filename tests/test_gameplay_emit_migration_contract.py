from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.event_emit import emit_gameplay_event


@dataclass
class _GameplayBusStub:
    calls: list[tuple[str, str, str, dict[str, Any]]]

    def emit(
        self,
        event_type: str,
        *,
        source_entity: str = "",
        source_behaviour: str = "",
        **payload: Any,
    ) -> dict[str, Any]:
        captured = dict(payload)
        self.calls.append((event_type, source_entity, source_behaviour, captured))
        return {"event_type": event_type, "payload": captured}


@dataclass
class _LegacyBusStub:
    calls: list[tuple[str, dict[str, Any]]]

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        captured = dict(payload)
        self.calls.append((event_type, captured))
        return {"event_type": event_type, "payload": captured}


def test_adapter_prefers_gameplay_bus_when_both_buses_exist() -> None:
    gameplay_bus = _GameplayBusStub(calls=[])
    legacy_bus = _LegacyBusStub(calls=[])
    ctx = type(
        "Ctx",
        (),
        {"gameplay_event_bus": gameplay_bus, "event_bus": legacy_bus},
    )()

    payload = {"k": "v", "n": 3}
    emit_gameplay_event(
        ctx,
        "combat_attack",
        payload,
        source_entity_id="player_01",
        source_behaviour="MigrationContract",
    )

    assert gameplay_bus.calls == [
        ("combat_attack", "player_01", "MigrationContract", {"k": "v", "n": 3})
    ]
    assert legacy_bus.calls == []


def test_adapter_falls_back_to_legacy_bus_when_gameplay_bus_missing() -> None:
    legacy_bus = _LegacyBusStub(calls=[])
    ctx = type("Ctx", (), {"event_bus": legacy_bus})()

    payload = {"zone": "hall_a"}
    emit_gameplay_event(
        ctx,
        "entered_zone",
        payload,
        source_entity_id="trigger_01",
        source_behaviour="MigrationContract",
    )

    assert legacy_bus.calls == [("entered_zone", {"zone": "hall_a"})]


def test_adapter_does_not_mutate_payload_identity_or_keys() -> None:
    gameplay_bus = _GameplayBusStub(calls=[])
    ctx = type("Ctx", (), {"gameplay_event_bus": gameplay_bus})()
    payload = {"nested": {"value": 1}, "items": [1, 2, 3]}
    payload_before = {"nested": {"value": 1}, "items": [1, 2, 3]}

    emit_gameplay_event(
        ctx,
        "dialogue_started",
        payload,
        source_entity_id="npc_mentor",
        source_behaviour="MigrationContract",
    )

    assert payload == payload_before
    assert gameplay_bus.calls == [
        (
            "dialogue_started",
            "npc_mentor",
            "MigrationContract",
            {"nested": {"value": 1}, "items": [1, 2, 3]},
        )
    ]
