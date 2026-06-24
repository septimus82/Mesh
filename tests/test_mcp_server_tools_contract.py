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


# ------------------------------------------------------------- batch action
def test_op_catalog_matches_apply_job_dispatch() -> None:
    """Drift guard: the catalog's op types must equal what apply_job dispatches."""
    import ast
    import inspect
    import textwrap

    from engine.ai_ops import AIOps

    src = textwrap.dedent(inspect.getsource(AIOps.apply_job))
    dispatched: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == "op_type"
        ):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    dispatched.add(comparator.value)
    assert dispatched, "expected to find op_type dispatch literals"
    assert set(tools.OP_CATALOG) == dispatched


def test_list_op_types_exposes_full_surface() -> None:
    rows = tools.list_op_types()
    types = [row["type"] for row in rows]
    assert types == sorted(types)
    assert set(types) == set(tools.OP_CATALOG)
    assert all({"type", "required", "optional", "summary"} <= set(row) for row in rows)


def test_apply_ops_batch_round_trip_with_validation(tmp_path) -> None:
    """A whole little scene built in ONE call, then validated."""
    import os

    prefabs_abs = os.path.abspath(os.path.join("assets", "prefabs.json"))
    prefab_name = tools.list_prefabs(".")[0]["display_name"]
    root = str(tmp_path)

    result = tools.apply_ops(
        [
            {"type": "create_scene", "name": "scenes/batch"},
            {"type": "add_entity_from_prefab", "scene_path": "scenes/batch.json",
             "prefab_name": prefab_name, "x": 10, "y": 10, "prefab_path": prefabs_abs},
            {"type": "add_entity_from_prefab", "scene_path": "scenes/batch.json",
             "prefab_name": prefab_name, "x": 40, "y": 40, "prefab_path": prefabs_abs},
        ],
        root=root,
        validate_scene_path="scenes/batch.json",
    )

    assert result["ok"] is True
    assert [r["type"] for r in result["results"]] == [
        "create_scene", "add_entity_from_prefab", "add_entity_from_prefab",
    ]
    assert all(r["ok"] for r in result["results"])
    assert "validation" in result and "ok" in result["validation"]
    assert tools.read_scene("scenes/batch.json", root=root)["entity_count"] == 2


def test_apply_ops_isolates_per_op_failures(tmp_path) -> None:
    root = str(tmp_path)
    result = tools.apply_ops(
        [
            {"type": "create_scene", "name": "scenes/mix"},
            {"type": "add_entity_from_prefab", "scene_path": "scenes/mix.json",
             "prefab_name": "__no_such_prefab__", "x": 0, "y": 0},
        ],
        root=root,
        validate=False,
    )
    assert result["ok"] is False  # overall fails because one op failed
    assert result["results"][0]["ok"] is True  # but the good op still ran
    assert result["results"][1]["ok"] is False
    assert "validation" not in result


# ------------------------------------------------------------- context resource
def test_engine_overview_json_is_valid_and_complete() -> None:
    import json

    payload = json.loads(tools.engine_overview_json("."))
    assert set(payload) == {"scenes", "prefabs", "behaviours", "operations"}
    assert payload["behaviours"], "overview must brief the model on behaviours"
    assert payload["operations"], "overview must brief the model on the op surface"


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
