"""Dependency-free tool logic for the Mesh MCP server.

Every function here returns plain JSON-serialisable data and imports nothing
from the ``mcp`` SDK, so the whole surface is unit-testable without a live MCP
client. :mod:`engine.mcp_server.server` registers these as MCP tools/resources.

Three families:

* **read** tools (the AI's eyes): ``list_scenes``, ``read_scene``,
  ``list_prefabs``, ``list_behaviours``.
* **action** tools (the AI's hands): ``create_scene``,
  ``add_entity_from_prefab`` — thin wrappers over :class:`engine.ai_ops.AIOps`.
* **safety**: ``validate_scene`` so writes can be checked.
* **context**: ``engine_overview`` — instant expertise as a resource.

All functions take a ``root`` base directory (default ``"."``) so they can be
pointed at a sandbox in tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _root_path(root: str) -> Path:
    return Path(root)


# Catalog of every operation `apply_ops` can run, mirroring the dispatch in
# engine.ai_ops.AIOps.apply_job. "required" fields are accessed via op["..."]
# (a KeyError if missing); "optional" via op.get(...). A drift-guard test
# asserts these type names match what apply_job actually dispatches.
OP_CATALOG: dict[str, dict[str, Any]] = {
    "create_scene": {"required": ["name"], "optional": ["template"], "summary": "Create a scene from a template."},
    "add_entity_from_prefab": {"required": ["scene_path", "prefab_name"], "optional": ["x", "y", "prefab_path"], "summary": "Place a prefab in a scene."},
    "delete_entity": {"required": ["scene_path", "entity_id"], "optional": [], "summary": "Remove an entity from a scene."},
    "set_behaviour_params": {"required": ["scene_path", "entity_id", "behaviour_name"], "optional": ["params"], "summary": "Set a behaviour's params."},
    "edit_dialogue": {"required": ["scene_path", "entity_id"], "optional": ["patch"], "summary": "Patch an entity's dialogue."},
    "edit_quest": {"required": ["quest_id"], "optional": ["patch", "quests_path"], "summary": "Patch a quest definition."},
    "add_quest_definition": {"required": ["quest_id"], "optional": ["quest", "quests_path"], "summary": "Add a quest definition."},
    "update_quest_definition": {"required": ["quest_id"], "optional": ["quest", "quests_path"], "summary": "Update a quest definition."},
    "delete_quest_definition": {"required": ["quest_id"], "optional": ["quests_path"], "summary": "Delete a quest definition."},
    "paint_tiles": {"required": ["scene_path"], "optional": ["ops"], "summary": "Apply tile paint operations to a scene."},
    "add_light": {"required": ["scene_path"], "optional": ["light"], "summary": "Add a light to a scene."},
    "update_light": {"required": ["scene_path"], "optional": ["index", "patch"], "summary": "Patch a light by index."},
    "delete_light": {"required": ["scene_path"], "optional": ["index"], "summary": "Delete a light by index."},
    "run_validation": {"required": [], "optional": ["scene_path"], "summary": "Validate a scene (or the whole world)."},
    "add_world_scene": {"required": ["scene_key", "path"], "optional": ["world_path", "label", "tags"], "summary": "Register a scene in the world."},
    "link_world_scenes": {"required": ["from_key", "to_key"], "optional": ["world_path", "via", "bidirectional"], "summary": "Link two world scenes."},
    "set_world_start": {"required": [], "optional": ["world_path", "start_scene", "start_spawn"], "summary": "Set the world start scene/spawn."},
    "add_cutscene": {"required": ["id"], "optional": ["steps", "cutscenes_path"], "summary": "Add a cutscene."},
    "update_cutscene": {"required": ["id"], "optional": ["steps", "cutscenes_path"], "summary": "Update a cutscene."},
    "delete_cutscene": {"required": ["id"], "optional": ["cutscenes_path"], "summary": "Delete a cutscene."},
    "insert_cutscene_step": {"required": ["id"], "optional": ["step", "index", "cutscenes_path"], "summary": "Insert a step into a cutscene."},
    "update_cutscene_step": {"required": ["id"], "optional": ["index", "patch", "cutscenes_path"], "summary": "Patch a cutscene step by index."},
    "delete_cutscene_step": {"required": ["id"], "optional": ["index", "cutscenes_path"], "summary": "Delete a cutscene step by index."},
}


# ---------------------------------------------------------------- read tools
def list_scenes(root: str = ".") -> list[str]:
    """List scene file paths (relative to ``root``) under ``scenes/``."""
    base = _root_path(root)
    scenes_dir = base / "scenes"
    if not scenes_dir.is_dir():
        return []
    return sorted(
        str(path.relative_to(base).as_posix())
        for path in scenes_dir.glob("*.json")
    )


def read_scene(scene_path: str, root: str = ".") -> dict[str, Any]:
    """Return the parsed scene JSON plus a small summary.

    ``scene_path`` is interpreted relative to ``root`` when not absolute.
    """
    base = _root_path(root)
    path = Path(scene_path)
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        return {"ok": False, "message": f"Scene not found: {scene_path}"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "message": f"Failed to read scene: {exc}"}
    entities = payload.get("entities") if isinstance(payload, dict) else None
    entity_count = len(entities) if isinstance(entities, list) else 0
    return {
        "ok": True,
        "scene_path": scene_path,
        "entity_count": entity_count,
        "scene": payload,
    }


def list_prefabs(root: str = ".") -> list[dict[str, str]]:
    """List available prefabs as ``{id, display_name}`` from assets/prefabs.json."""
    base = _root_path(root)
    path = base / "assets" / "prefabs.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = raw.values() if isinstance(raw, dict) else raw
    if not isinstance(entries, (list, tuple)) and not hasattr(entries, "__iter__"):
        return []
    rows: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        prefab_id = str(entry.get("id") or entry.get("name") or "")
        if not prefab_id:
            continue
        rows.append(
            {
                "id": prefab_id,
                "display_name": str(entry.get("display_name") or prefab_id),
            }
        )
    return sorted(rows, key=lambda row: row["id"])


def list_behaviours() -> list[str]:
    """List every registered behaviour name (builtins force-loaded)."""
    from engine.behaviours import BEHAVIOUR_REGISTRY, load_builtin_behaviours

    load_builtin_behaviours(force=True)
    return sorted(BEHAVIOUR_REGISTRY)


# -------------------------------------------------------------- action tools
def _result_to_dict(result: Any) -> dict[str, Any]:
    return {
        "ok": bool(getattr(result, "ok", False)),
        "message": str(getattr(result, "message", "")),
        "data": getattr(result, "data", None),
    }


def create_scene(name: str, template: str = "empty", root: str = ".") -> dict[str, Any]:
    """Create a new scene from a template. Wraps ``AIOps.create_scene``."""
    from engine.ai_ops import AIOps

    return _result_to_dict(AIOps(base_dir=root).create_scene(name, template))


def add_entity_from_prefab(
    scene_path: str,
    prefab_name: str,
    x: float,
    y: float,
    prefab_path: str | None = None,
    root: str = ".",
) -> dict[str, Any]:
    """Place a prefab instance into a scene. Wraps ``AIOps.add_entity_from_prefab``.

    ``prefab_name`` matches a prefab's ``display_name`` or ``name``.
    ``prefab_path`` optionally points at the prefab palette file to resolve
    from (e.g. ``assets/prefabs.json``); when omitted the engine's default
    palette is used.
    """
    from engine.ai_ops import AIOps

    result = AIOps(base_dir=root).add_entity_from_prefab(
        scene_path, prefab_name, float(x), float(y), prefab_path=prefab_path
    )
    return _result_to_dict(result)


# -------------------------------------------------------------- batch action
def list_op_types() -> list[dict[str, Any]]:
    """List every operation `apply_ops` accepts, with required/optional fields.

    Lets a connected model see the full action surface and field shapes up
    front, so it builds well-formed operations instead of guessing.
    """
    return [
        {"type": op_type, **spec}
        for op_type, spec in sorted(OP_CATALOG.items())
    ]


def apply_ops(
    operations: list[dict[str, Any]],
    root: str = ".",
    validate: bool = True,
    validate_scene_path: str | None = None,
) -> dict[str, Any]:
    """Run a batch of operations in one call, then validate.

    ``operations`` is a list of ``{"type": <op>, ...fields}`` dicts (see
    :func:`list_op_types`). Wraps :meth:`engine.ai_ops.AIOps.apply_job`, echoing
    each operation's ``type`` into its result, and — when ``validate`` is true —
    appends a validation pass so the model gets immediate, structured feedback
    on whether the batch left the content valid.

    Returns ``{ok, results: [{type, ok, message, data}], validation?}``. Per-op
    failures are isolated (one bad op does not abort the rest); ``ok`` is the
    AND of every operation's success.
    """
    from engine.ai_ops import AIOps

    ops_runner = AIOps(base_dir=root)
    outcome = ops_runner.apply_job({"operations": list(operations)})

    annotated: list[dict[str, Any]] = []
    raw_results = outcome.get("results", []) if isinstance(outcome, dict) else []
    for op, result in zip(operations, raw_results):
        entry = dict(result) if isinstance(result, dict) else {"ok": False, "message": str(result)}
        if isinstance(op, dict):
            entry["type"] = op.get("type")
        annotated.append(entry)

    payload: dict[str, Any] = {
        "ok": bool(outcome.get("ok", False)) if isinstance(outcome, dict) else False,
        "results": annotated,
    }
    if validate:
        payload["validation"] = _result_to_dict(
            ops_runner.run_validation(validate_scene_path)
        )
    return payload


# ---------------------------------------------------------------- safety
def validate_scene(scene_path: str | None = None, root: str = ".") -> dict[str, Any]:
    """Validate a scene (or the whole world if ``scene_path`` is None)."""
    from engine.ai_ops import AIOps

    return _result_to_dict(AIOps(base_dir=root).run_validation(scene_path))


# ---------------------------------------------------------------- context
def engine_overview(root: str = ".") -> dict[str, Any]:
    """A compact expert briefing: scenes, prefabs, and behaviours available.

    Served as an MCP resource so a freshly-connected model is immediately
    fluent in what this engine contains and what it can build.
    """
    return {
        "scenes": list_scenes(root),
        "prefabs": list_prefabs(root),
        "behaviours": list_behaviours(),
        "operations": list_op_types(),
    }


def engine_overview_json(root: str = ".") -> str:
    """``engine_overview`` rendered as a JSON string (for MCP resource bodies)."""
    return json.dumps(engine_overview(root), indent=2, sort_keys=True)
