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
    }


def engine_overview_json(root: str = ".") -> str:
    """``engine_overview`` rendered as a JSON string (for MCP resource bodies)."""
    return json.dumps(engine_overview(root), indent=2, sort_keys=True)
