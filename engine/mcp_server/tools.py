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


def _entity_summary(entity: dict[str, Any]) -> dict[str, Any]:
    """Compact, identity-first view of one entity."""
    behaviours = entity.get("behaviours")
    return {
        "name": str(entity.get("name")) if entity.get("name") is not None else None,
        "id": entity.get("id"),
        "tag": entity.get("tag"),
        "sprite": entity.get("sprite"),
        "x": entity.get("x"),
        "y": entity.get("y"),
        "behaviours": list(behaviours) if isinstance(behaviours, list) else [],
    }


def list_entities(scene_path: str, root: str = ".") -> dict[str, Any]:
    """List a scene's entities as compact summaries (name, tag, pos, behaviours).

    ``name`` is the identifier the action ops use — ``inspect_entity``,
    ``delete_entity``, and ``set_behaviour_params`` all key on it.
    """
    loaded = read_scene(scene_path, root)
    if not loaded.get("ok"):
        return {"ok": False, "message": loaded.get("message", "Scene not found")}
    scene = loaded.get("scene")
    entities = scene.get("entities") if isinstance(scene, dict) else None
    summaries = [
        _entity_summary(entity)
        for entity in (entities or [])
        if isinstance(entity, dict)
    ]
    return {"ok": True, "scene_path": scene_path, "count": len(summaries), "entities": summaries}


def inspect_entity(scene_path: str, entity_id: str, root: str = ".") -> dict[str, Any]:
    """Return one entity in full detail so the AI can see what it built.

    ``entity_id`` matches the entity's ``name`` field (the same identity the
    action ops use). Returns a compact summary plus ``behaviour_config`` and the
    full raw ``entity`` dict — closing the build -> inspect -> refine loop.
    """
    loaded = read_scene(scene_path, root)
    if not loaded.get("ok"):
        return {"ok": False, "message": loaded.get("message", "Scene not found")}
    scene = loaded.get("scene")
    entities = scene.get("entities") if isinstance(scene, dict) else None
    for entity in (entities or []):
        if isinstance(entity, dict) and str(entity.get("name")) == entity_id:
            summary = _entity_summary(entity)
            behaviour_config = entity.get("behaviour_config")
            return {
                "ok": True,
                "scene_path": scene_path,
                **summary,
                "behaviour_config": behaviour_config if isinstance(behaviour_config, dict) else {},
                "entity": entity,
            }
    return {"ok": False, "message": f"Entity '{entity_id}' not found in {scene_path}"}


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


def _load_quests(root: str) -> list[dict[str, Any]]:
    """Load quest definitions from assets/data/quests.json across known shapes."""
    path = _root_path(root) / "assets" / "data" / "quests.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        quests = raw.get("quests")
        if isinstance(quests, list):
            return [q for q in quests if isinstance(q, dict)]
        # Legacy {quest_id: {...}} mapping.
        result: list[dict[str, Any]] = []
        for key, value in raw.items():
            if isinstance(value, dict):
                entry = dict(value)
                entry.setdefault("id", key)
                result.append(entry)
        return result
    if isinstance(raw, list):
        return [q for q in raw if isinstance(q, dict)]
    return []


def list_quests(root: str = ".") -> dict[str, Any]:
    """List quest definitions as compact summaries (id, title, stage count).

    ``id`` is the identifier the quest action ops (``edit_quest``,
    ``update_quest_definition``, ``delete_quest_definition``) key on.
    """
    summaries: list[dict[str, Any]] = []
    for quest in _load_quests(root):
        quest_id = quest.get("id")
        if not isinstance(quest_id, str) or not quest_id.strip():
            continue
        stages = quest.get("stages")
        summaries.append(
            {
                "id": quest_id,
                "title": quest.get("title"),
                "stage_count": len(stages) if isinstance(stages, list) else 0,
            }
        )
    summaries.sort(key=lambda row: row["id"])
    return {"ok": True, "count": len(summaries), "quests": summaries}


def inspect_quest(quest_id: str, root: str = ".") -> dict[str, Any]:
    """Return one quest in full detail so the AI can refine it.

    Includes a compact stage list (id + title) plus the full raw ``quest`` dict.
    """
    for quest in _load_quests(root):
        if str(quest.get("id")) == quest_id:
            stages = quest.get("stages")
            stage_rows = [
                {"id": stage.get("id"), "title": stage.get("title")}
                for stage in (stages or [])
                if isinstance(stage, dict)
            ]
            return {
                "ok": True,
                "id": quest_id,
                "title": quest.get("title"),
                "description": quest.get("description"),
                "stages": stage_rows,
                "quest": quest,
            }
    return {"ok": False, "message": f"Quest '{quest_id}' not found"}


def list_lights(scene_path: str, root: str = ".") -> dict[str, Any]:
    """List a scene's lights with their index and key fields.

    ``index`` is the identifier the light action ops (``update_light``,
    ``delete_light``) key on, so the AI can list then refine a specific light.
    """
    loaded = read_scene(scene_path, root)
    if not loaded.get("ok"):
        return {"ok": False, "message": loaded.get("message", "Scene not found")}
    scene = loaded.get("scene")
    lights = scene.get("lights") if isinstance(scene, dict) else None
    rows: list[dict[str, Any]] = []
    for index, light in enumerate(lights or []):
        if not isinstance(light, dict):
            continue
        rows.append(
            {
                "index": index,
                "id": light.get("id"),
                "type": light.get("type"),
                "x": light.get("x"),
                "y": light.get("y"),
                "radius": light.get("radius"),
                "color": light.get("color"),
                "enabled": light.get("enabled"),
            }
        )
    return {"ok": True, "scene_path": scene_path, "count": len(rows), "lights": rows}


def read_dialogue(scene_path: str, entity_id: str, root: str = ".") -> dict[str, Any]:
    """Return an entity's dialogue block (the read counterpart to ``edit_dialogue``).

    ``entity_id`` matches the entity's ``name`` (the same identity
    ``inspect_entity`` and ``edit_dialogue`` use). The dialogue dict is returned
    verbatim (no fixed schema assumed). Looks at the entity-level ``dialogue``
    key first, then ``behaviour_config["Dialogue"]["dialogue"]`` (where
    ``edit_dialogue`` writes). Never raises.
    """
    loaded = read_scene(scene_path, root)
    if not loaded.get("ok"):
        return {"ok": False, "message": loaded.get("message", f"Scene not found: {scene_path}")}
    scene = loaded.get("scene")
    entities = scene.get("entities") if isinstance(scene, dict) else None
    for entity in (entities or []):
        if not isinstance(entity, dict) or str(entity.get("name")) != entity_id:
            continue
        dialogue = entity.get("dialogue")
        if not isinstance(dialogue, dict):
            config = entity.get("behaviour_config")
            if isinstance(config, dict):
                inner = config.get("Dialogue")
                if isinstance(inner, dict) and isinstance(inner.get("dialogue"), dict):
                    dialogue = inner["dialogue"]
        has_dialogue = isinstance(dialogue, dict) and bool(dialogue)
        return {
            "ok": True,
            "scene_path": scene_path,
            "entity_id": entity_id,
            "has_dialogue": has_dialogue,
            "dialogue": dialogue if isinstance(dialogue, dict) else None,
        }
    return {"ok": False, "message": f"Entity '{entity_id}' not found in {scene_path}"}


def read_world(world_path: str | None = None, root: str = ".") -> dict[str, Any]:
    """Return the world graph (the read counterpart to the world write ops).

    Mirrors ``add_world_scene`` / ``link_world_scenes`` / ``set_world_start``:
    keyed on ``world_path`` (default ``worlds/main_world.json``, matching
    ``AIOps``), resolved relative to ``root``. Never raises.
    """
    base = _root_path(root)
    rel = world_path or "worlds/main_world.json"
    path = Path(rel)
    if not path.is_absolute():
        path = base / path
    if not path.is_file():
        return {"ok": False, "message": f"World not found: {rel}"}
    try:
        world = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "message": f"Failed to read world: {exc}"}
    if not isinstance(world, dict):
        return {"ok": False, "message": f"World file is not an object: {rel}"}

    scenes_raw = world.get("scenes")
    scenes: list[dict[str, Any]] = []
    if isinstance(scenes_raw, dict):
        for key in sorted(scenes_raw):
            entry = scenes_raw[key]
            if not isinstance(entry, dict):
                continue
            scenes.append(
                {
                    "key": key,
                    "path": entry.get("path"),
                    "label": entry.get("label"),
                    "tags": entry.get("tags") if isinstance(entry.get("tags"), list) else [],
                }
            )

    links_raw = world.get("links")
    links: list[dict[str, Any]] = []
    if isinstance(links_raw, list):
        for link in links_raw:
            if isinstance(link, dict):
                links.append({"from": link.get("from"), "to": link.get("to"), "via": link.get("via")})

    return {
        "ok": True,
        "world_path": rel,
        "start_scene": world.get("start_scene"),
        "start_spawn": world.get("start_spawn"),
        "scenes": scenes,
        "links": links,
    }


_TILEMAP_DIMENSION_KEYS = (
    "width",
    "height",
    "tile_size",
    "tile_width",
    "tile_height",
    "cols",
    "rows",
    "columns",
)


def read_tilemap(scene_path: str, root: str = ".") -> dict[str, Any]:
    """Return a scene's tilemap structure (the read counterpart to ``paint_tiles``).

    Keyed on ``scene_path`` (same identity ``paint_tiles`` uses). Reads
    ``scene["tilemap"]`` (falling back to ``settings["tilemap"]``) and returns the
    layers (name/z), per-layer tile arrays (from ``overrides.layers``), the
    collision layer id, and any dimension fields present. No tilemap is not an
    error (``has_tilemap`` False). Never raises.
    """
    loaded = read_scene(scene_path, root)
    if not loaded.get("ok"):
        return {"ok": False, "message": loaded.get("message", f"Scene not found: {scene_path}")}
    scene = loaded.get("scene")
    scene_dict: dict[str, Any] = scene if isinstance(scene, dict) else {}

    tilemap = scene_dict.get("tilemap")
    if not isinstance(tilemap, dict):
        settings = scene_dict.get("settings")
        candidate = settings.get("tilemap") if isinstance(settings, dict) else None
        if isinstance(candidate, dict):
            tilemap = candidate
        elif candidate:
            # A bare tilemap path reference (no inline layer data).
            return {
                "ok": True,
                "scene_path": scene_path,
                "has_tilemap": True,
                "collision_layer_id": None,
                "layers": [],
                "tiles": {},
                "path": candidate,
                "dimensions": {},
            }
        else:
            return {"ok": True, "scene_path": scene_path, "has_tilemap": False}

    layers_raw = tilemap.get("layers")
    layers: list[dict[str, Any]] = []
    if isinstance(layers_raw, list):
        for layer in layers_raw:
            if isinstance(layer, dict):
                layers.append({"name": layer.get("name"), "z": layer.get("z")})

    tiles: dict[str, Any] = {}
    overrides = tilemap.get("overrides")
    if isinstance(overrides, dict):
        override_layers = overrides.get("layers")
        if isinstance(override_layers, dict):
            tiles = {str(name): values for name, values in override_layers.items()}

    dimensions = {key: tilemap[key] for key in _TILEMAP_DIMENSION_KEYS if key in tilemap}

    return {
        "ok": True,
        "scene_path": scene_path,
        "has_tilemap": True,
        "collision_layer_id": tilemap.get("collision_layer_id"),
        "layers": layers,
        "tiles": tiles,
        "path": tilemap.get("path"),
        "dimensions": dimensions,
    }


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


# ----------------------------------------------------------- playability
_ENEMY_BEHAVIOURS = ("EnemyAI", "ChaseTarget")
# Effective default target_tag per enemy behaviour when none is configured.
# (EnemyAI defaults to "player"; ChaseTarget defaults to "" i.e. targets nothing.)
_ENEMY_DEFAULT_TARGET_TAG = {"EnemyAI": "player", "ChaseTarget": ""}


def _behaviour_names(entity: dict[str, Any]) -> list[str]:
    behaviours = entity.get("behaviours")
    return [str(b) for b in behaviours] if isinstance(behaviours, list) else []


def _behaviour_config(entity: dict[str, Any], name: str) -> dict[str, Any]:
    config = entity.get("behaviour_config")
    if isinstance(config, dict):
        inner = config.get(name)
        if isinstance(inner, dict):
            return inner
    return {}


def _scene_has_tilemap(scene: dict[str, Any]) -> bool:
    if scene.get("tilemap"):
        return True
    settings = scene.get("settings")
    return bool(isinstance(settings, dict) and settings.get("tilemap"))


def playability_check(scene_path: str, root: str = ".") -> dict[str, Any]:
    """Advisory: does this scene *feel* playable (tagged player + camera + enemy)?

    Resolves prefab references (via :class:`engine.prefabs.PrefabManager`) so the
    check sees MERGED entities -- it works for AI-placed inline entities *and*
    ``prefab_id``-referenced ones. Findings are WARNINGS, never hard failures:
    ``ok`` is ``True`` only when there are no warnings, but ``ok=False`` just
    means "not fully playable yet", not an error. A missing scene returns a
    structured ``{"ok": False, "message": ...}`` rather than raising.
    """
    loaded = read_scene(scene_path, root)
    if not loaded.get("ok"):
        return {"ok": False, "message": loaded.get("message", f"Scene not found: {scene_path}")}

    scene_obj = loaded.get("scene")
    scene: dict[str, Any] = scene_obj if isinstance(scene_obj, dict) else {}
    raw_entities = scene.get("entities")
    entities = [e for e in (raw_entities or []) if isinstance(e, dict)]

    from engine.prefabs import get_prefab_manager

    manager = get_prefab_manager()
    resolved: list[dict[str, Any]] = []
    for entity in entities:
        try:
            merged = manager.resolve(entity)
        except Exception:  # noqa: BLE001  # REASON: advisory tool must never raise on content
            merged = entity
        resolved.append(merged if isinstance(merged, dict) else entity)

    # --- player ---
    players = [e for e in resolved if str(e.get("tag") or "") == "player"]
    has_player = bool(players)
    player_has_camera = any("CameraFollow" in _behaviour_names(e) for e in players)
    player_tags = {str(e.get("tag")) for e in players if e.get("tag")} or {"player"}

    # --- enemies able to target the player ---
    enemies_targeting = 0
    enemyai_targeting = 0
    chasetarget_targeting = 0
    for entity in resolved:
        names = _behaviour_names(entity)
        for enemy_behaviour in _ENEMY_BEHAVIOURS:
            if enemy_behaviour not in names:
                continue
            config = _behaviour_config(entity, enemy_behaviour)
            target_tag = str(
                config.get("target_tag", _ENEMY_DEFAULT_TARGET_TAG[enemy_behaviour]) or ""
            )
            if target_tag and target_tag in player_tags:
                enemies_targeting += 1
                if enemy_behaviour == "EnemyAI":
                    enemyai_targeting += 1
                else:
                    chasetarget_targeting += 1

    warnings: list[str] = []
    if not has_player:
        warnings.append(
            'No entity is tagged "player"; the camera has nothing to follow and '
            "enemies have nothing to target."
        )
    elif not player_has_camera:
        warnings.append(
            "A player is present but has no CameraFollow behaviour; the camera won't "
            "follow the player."
        )

    if enemies_targeting == 0:
        warnings.append(
            "No enemy can target the player (add an entity with EnemyAI or ChaseTarget "
            "whose target_tag matches the player's tag)."
        )
    elif chasetarget_targeting > 0 and enemyai_targeting == 0 and not _scene_has_tilemap(scene):
        warnings.append(
            "The only player-targeting enemy uses ChaseTarget but the scene has no "
            "tilemap; ChaseTarget needs a nav grid (tilemap) to path, so the chase will "
            "be inert. Use EnemyAI for collision-based chasing without a tilemap."
        )

    return {
        "ok": not warnings,
        "scene_path": scene_path,
        "warnings": warnings,
        "summary": {
            "has_player": has_player,
            "player_has_camera": player_has_camera,
            "enemies_targeting_player": enemies_targeting,
        },
    }


# ---------------------------------------------------------------- context
def list_scene_templates() -> list[str]:
    """List the template names ``create_scene`` accepts.

    Read live from the scaffold registry (:data:`engine.tooling.scaffold.TEMPLATES`)
    so the surfaced list can never drift from what the tool actually supports.
    """
    from engine.tooling.scaffold import TEMPLATES

    return sorted(TEMPLATES.keys())


def playable_scene_recipe() -> list[dict[str, Any]]:
    """An ordered, engine-accurate recipe for assembling a *playable* scene.

    Every prefab id referenced here (``prefab`` field) is a real prefab in
    ``assets/prefabs.json`` (guarded by the tool contract tests), so a connected
    model can follow these steps with the existing tools/prefabs only.
    """
    return [
        {
            "step": 1,
            "tool": "create_scene",
            "prefab": None,
            "detail": "Create a scene. Pass a template from `scene_templates` (e.g. \"empty\").",
        },
        {
            "step": 2,
            "tool": "add_entity_from_prefab",
            "prefab": "player",
            "detail": (
                "Add the \"player\" prefab. It already includes PlayerController + CameraFollow "
                "and tag \"player\", so the camera follows it and enemies can target it."
            ),
        },
        {
            "step": 3,
            "tool": "add_entity_from_prefab",
            "prefab": "chaser_enemy",
            "detail": (
                "Add at least one enemy, e.g. the \"chaser_enemy\" prefab (EnemyAI chases the "
                "nearest entity tagged \"player\"; collision-based, so it works without a tilemap)."
            ),
        },
        {
            "step": 4,
            "tool": "validate_scene",
            "prefab": None,
            "detail": "Validate the scene to confirm the batch left it valid.",
        },
    ]


def engine_overview(root: str = ".") -> dict[str, Any]:
    """A compact expert briefing: scenes, prefabs, and behaviours available.

    Served as an MCP resource so a freshly-connected model is immediately
    fluent in what this engine contains, what it can build, and *how* to build a
    playable scene (the recipe + the create_scene template names).
    """
    return {
        "scenes": list_scenes(root),
        "prefabs": list_prefabs(root),
        "behaviours": list_behaviours(),
        "operations": list_op_types(),
        "scene_templates": list_scene_templates(),
        "playable_scene_recipe": playable_scene_recipe(),
    }


def engine_overview_json(root: str = ".") -> str:
    """``engine_overview`` rendered as a JSON string (for MCP resource bodies)."""
    return json.dumps(engine_overview(root), indent=2, sort_keys=True)
