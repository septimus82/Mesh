from __future__ import annotations

from engine.editor.event_monitor_model import (
    build_event_log_view_model,
    build_event_log_view_model_from_settings,
    build_event_monitor_lines,
)
from engine.gameplay_event_bus import GameplayEventBus
from engine.workspace_settings import WorkspaceSettings


def test_event_monitor_filters_and_orders_events() -> None:
    bus = GameplayEventBus()
    bus.emit("alpha", source_entity="hero", source_behaviour="Test", foo=1)
    bus.emit("beta", source_entity="hero", source_behaviour="Test", bar=2)
    bus.emit("gamma", source_entity="npc", source_behaviour="Test", baz=3)
    bus.emit("delta", source_entity="hero", source_behaviour="Test")
    bus.drain()

    view_model = build_event_log_view_model(bus, event_type_filter="a", limit=2)
    assert [row.event_type for row in view_model.rows] == ["gamma", "delta"]

    entity_model = build_event_log_view_model(bus, entity_id="hero", limit=10)
    assert [row.event_type for row in entity_model.rows] == ["alpha", "beta", "delta"]

    lines = build_event_monitor_lines(entity_model)
    assert lines[0] == "Event Monitor"
    assert lines[1].startswith("Type Filter")
    assert lines[4].startswith("Events: 3/")


def test_event_monitor_reads_filters_from_workspace_settings() -> None:
    bus = GameplayEventBus()
    bus.emit("alpha", source_entity="hero", source_behaviour="Test")
    bus.emit("beta", source_entity="npc", source_behaviour="Test")
    bus.drain()

    settings = WorkspaceSettings(
        debug_event_type_filter="b",
        debug_event_entity_id="npc",
        debug_event_limit=5,
    )
    view_model = build_event_log_view_model_from_settings(bus, settings)
    assert view_model.event_type_filter == "b"
    assert view_model.entity_id == "npc"
    assert view_model.limit == 5
    assert [row.event_type for row in view_model.rows] == ["beta"]
