"""Contract tests for debug workspace settings persistence."""

from __future__ import annotations

import json

from engine.workspace_settings import WorkspaceSettings, load_workspace, save_workspace


def test_workspace_debug_settings_defaults_are_namespaced() -> None:
    settings = WorkspaceSettings()
    assert settings.debug_event_type_filter == ""
    assert settings.debug_event_entity_id == ""
    assert settings.debug_event_limit == 20


def test_workspace_debug_settings_roundtrip(tmp_path) -> None:
    settings = WorkspaceSettings(
        debug_event_type_filter="combat",
        debug_event_entity_id="hero_01",
        debug_event_limit=7,
    )
    save_workspace(tmp_path, settings)

    data = json.loads((tmp_path / "workspace.json").read_text("utf-8"))
    assert "debug_event_type_filter" in data
    assert "debug_event_entity_id" in data
    assert "debug_event_limit" in data

    loaded = load_workspace(tmp_path)
    assert loaded.debug_event_type_filter == "combat"
    assert loaded.debug_event_entity_id == "hero_01"
    assert loaded.debug_event_limit == 7


def test_workspace_debug_settings_clamp_invalid_limit() -> None:
    settings = WorkspaceSettings.from_dict({"debug_event_limit": -5})
    assert settings.debug_event_limit == 0

    settings = WorkspaceSettings.from_dict({"debug_event_limit": "invalid"})
    assert settings.debug_event_limit == 20
