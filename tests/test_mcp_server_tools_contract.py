"""Contract tests for the Mesh MCP server tool surface.

These exercise the *logic* in :mod:`engine.mcp_server.tools` directly, with no
live MCP client and no dependency on the optional ``mcp`` SDK. A separate test
covers the FastMCP wiring's import guard.
"""

from __future__ import annotations

import os

import pytest

from engine.mcp_server import tools


# --------------------------------------------------------------- read tools
def test_list_scenes_returns_scene_paths() -> None:
    scenes = tools.list_scenes(".")
    assert scenes, "expected at least one scene under scenes/"
    assert all(path.startswith("scenes/") and path.endswith(".json") for path in scenes)


def test_read_scene_returns_summary_and_payload() -> None:
    scenes = tools.list_scenes(".")
    result = tools.read_scene(scenes[0], ".")
    assert result["ok"] is True
    assert "entity_count" in result
    assert isinstance(result["scene"], dict)


def test_read_scene_missing_is_structured_not_raised() -> None:
    result = tools.read_scene("scenes/__does_not_exist__.json", ".")
    assert result["ok"] is False
    assert "not found" in result["message"].lower()


def test_list_prefabs_returns_id_and_display_name() -> None:
    prefabs = tools.list_prefabs(".")
    assert prefabs, "expected prefabs from assets/prefabs.json"
    assert all(set(row) == {"id", "display_name"} for row in prefabs)
    ids = [row["id"] for row in prefabs]
    assert ids == sorted(ids), "prefabs should be sorted by id"


def test_list_behaviours_covers_registry() -> None:
    from engine.behaviours import BEHAVIOUR_REGISTRY, load_builtin_behaviours

    load_builtin_behaviours(force=True)
    names = tools.list_behaviours()
    assert names == sorted(names)
    assert set(names) == set(BEHAVIOUR_REGISTRY)


# ------------------------------------------------------------- action round-trip
def test_build_round_trip_create_add_validate(tmp_path) -> None:
    """The core vision in miniature: read -> build -> see the result -> validate."""
    prefabs_abs = os.path.abspath(os.path.join("assets", "prefabs.json"))
    palette = tools.list_prefabs(".")
    prefab_name = palette[0]["display_name"]
    root = str(tmp_path)

    created = tools.create_scene("scenes/round_trip", root=root)
    assert created["ok"] is True

    added = tools.add_entity_from_prefab(
        "scenes/round_trip.json", prefab_name, 10.0, 10.0,
        prefab_path=prefabs_abs, root=root,
    )
    assert added["ok"] is True, added["message"]

    after = tools.read_scene("scenes/round_trip.json", root=root)
    assert after["entity_count"] == 1

    validated = tools.validate_scene("scenes/round_trip.json", root=root)
    assert "ok" in validated  # validation runs and returns a structured verdict


def test_add_entity_unknown_prefab_is_structured_not_raised(tmp_path) -> None:
    root = str(tmp_path)
    tools.create_scene("scenes/s", root=root)
    result = tools.add_entity_from_prefab(
        "scenes/s.json", "__no_such_prefab__", 0.0, 0.0, root=root,
    )
    assert result["ok"] is False
    assert "not found" in result["message"].lower()


# ------------------------------------------------------------- context resource
def test_engine_overview_json_is_valid_and_complete() -> None:
    import json

    payload = json.loads(tools.engine_overview_json("."))
    assert set(payload) == {"scenes", "prefabs", "behaviours"}
    assert payload["behaviours"], "overview must brief the model on behaviours"


# ------------------------------------------------------------- server guard
def test_server_build_raises_without_mcp(monkeypatch) -> None:
    from engine.mcp_server import server

    monkeypatch.setattr(server, "HAS_MCP", False)
    monkeypatch.setattr(server, "FastMCP", None)
    with pytest.raises(RuntimeError, match="mcp"):
        server.build_server()


def test_server_build_succeeds_when_mcp_present() -> None:
    from engine.mcp_server import server

    if not server.HAS_MCP:
        pytest.skip("optional mcp SDK not installed")
    built = server.build_server()
    assert built is not None
