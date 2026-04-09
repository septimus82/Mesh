"""World management commands."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.tooling import graph, validate_all
from engine.tooling.auto_wire import AutoWireController


def _handle_validate_world(args: argparse.Namespace) -> int:
    """Validate world structure and links."""
    world_path = Path(args.world_path)
    if not world_path.exists():
        print(f"World file not found: {world_path}")
        return 1

    try:
        with open(world_path, "r") as f:
            world = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Failed to parse world JSON: {e}")
        return 1

    # Use UnifiedValidator for consistent checks
    check_events = not args.no_events
    validator = validate_all.UnifiedValidator(Path("."), check_events=check_events)
    validator.validate_world(world_path, world)

    return validator.print_report()


def _handle_world_add_scene(args: argparse.Namespace) -> int:
    """Add or update a scene entry in a world file (idempotent)."""
    world_path = str(getattr(args, "world_path", "") or "").strip()
    if not world_path:
        print("[Mesh][CLI] Error: missing world_path")
        return 2

    scene_key = str(getattr(args, "key", "") or "").strip()
    if not scene_key:
        print("[Mesh][CLI] Error: missing --key")
        return 2

    scene_path = str(getattr(args, "path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing --path")
        return 2

    resolved_world = resolve_path(world_path)
    if not resolved_world.exists():
        print(f"[Mesh][CLI] Error: world not found: {normalize_scene_path(world_path)}")
        return 1

    try:
        raw_world = json.loads(resolved_world.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: world CLI should report world JSON parse failures deterministically before validating the world structure
        print(f"[Mesh][CLI] Error: failed to parse world JSON: {normalize_scene_path(world_path)}: {exc}")
        return 1

    if not isinstance(raw_world, dict):
        print(f"[Mesh][CLI] Error: world JSON root must be an object: {normalize_scene_path(world_path)}")
        return 1

    scenes = raw_world.get("scenes")
    if scenes is None:
        scenes = {}
        raw_world["scenes"] = scenes
    if not isinstance(scenes, dict):
        print(f"[Mesh][CLI] Error: world.scenes must be an object: {normalize_scene_path(world_path)}")
        return 1

    normalized_scene_path_val = normalize_scene_path(scene_path)

    existing = scenes.get(scene_key)
    changed = False
    if existing is None:
        scenes[scene_key] = {"path": normalized_scene_path_val}
        changed = True
    else:
        if not isinstance(existing, dict):
            print(f"[Mesh][CLI] Error: world.scenes[{scene_key!r}] must be an object")
            return 1
        if existing.get("path") != normalized_scene_path_val:
            existing["path"] = normalized_scene_path_val
            changed = True

    if not changed:
        return 0

    write_json_atomic(resolved_world, raw_world, indent=2, sort_keys=True, trailing_newline=True)
    print(f"[Mesh][CLI] OK: world updated: {normalize_scene_path(world_path)} key={scene_key} path={normalized_scene_path_val}")
    return 0


def _scene_transition_config(
    *,
    target_scene: str,
    spawn_id: str,
    x: float,
    y: float,
    name: str,
    entity_id: str,
) -> dict[str, Any]:
    return {
        "id": entity_id,
        "name": name,
        "tag": "trigger",
        "x": float(x),
        "y": float(y),
        "behaviours": [{"type": "SceneTransition", "params": {}}],
        "behaviour_config": {
            "SceneTransition": {
                "allow_interact": True,
                "spawn_id": str(spawn_id or ""),
                "target_scene": str(target_scene or ""),
            }
        },
    }


def _ensure_scene_transition_entity(
    *,
    entities: list,
    entity_id: str,
    target_scene: str,
    spawn_id: str,
    x: float,
    y: float,
    name: str,
) -> tuple[bool, str | None]:
    """Return (changed, error_message)."""
    existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
    if existing is None:
        entities.append(
            _scene_transition_config(
                target_scene=target_scene,
                spawn_id=spawn_id,
                x=x,
                y=y,
                name=name,
                entity_id=entity_id,
            )
        )
        return True, None
    if not isinstance(existing, dict):
        return False, f"entity '{entity_id}' exists but is not an object"

    mismatches: list[str] = []
    if existing.get("x") != float(x):
        mismatches.append("x")
    if existing.get("y") != float(y):
        mismatches.append("y")
    if str(existing.get("name") or "") != str(name):
        mismatches.append("name")
    if str(existing.get("tag") or "") != "trigger":
        mismatches.append("tag")

    behaviours = existing.get("behaviours")
    if not isinstance(behaviours, list) or not any(
        (isinstance(b, str) and b == "SceneTransition") or (isinstance(b, dict) and b.get("type") == "SceneTransition")
        for b in behaviours
    ):
        mismatches.append("behaviours")

    cfg_root = existing.get("behaviour_config")
    cfg = cfg_root.get("SceneTransition") if isinstance(cfg_root, dict) else None
    if not isinstance(cfg, dict):
        mismatches.append("behaviour_config.SceneTransition")
        cfg = {}

    if str(cfg.get("target_scene") or "") != str(target_scene):
        mismatches.append("SceneTransition.target_scene")
    if str(cfg.get("spawn_id") or cfg.get("spawn_point") or "") != str(spawn_id or ""):
        mismatches.append("SceneTransition.spawn_id")
    allow_interact = cfg.get("allow_interact")
    if allow_interact is not None and bool(allow_interact) is not True:
        mismatches.append("SceneTransition.allow_interact")

    if mismatches:
        mismatches = sorted(set(mismatches))
        return False, f"entity '{entity_id}' exists but differs: {', '.join(mismatches)}"

    return False, None


def _handle_world_link_scenes(args: argparse.Namespace) -> int:
    """Insert SceneTransition entities into scenes for a world link (idempotent)."""
    # Import here to avoid circular imports if any, though scene_commands is used in legacy
    from . import scene as scene_commands

    world_path = str(getattr(args, "world_path", "") or "").strip()
    if not world_path:
        print("[Mesh][CLI] Error: missing world_path")
        return 2

    from_key = str(getattr(args, "from_key", "") or "").strip()
    to_key = str(getattr(args, "to_key", "") or "").strip()
    if not from_key or not to_key:
        print("[Mesh][CLI] Error: missing --from-key/--to-key")
        return 2

    from_scene = str(getattr(args, "from_scene", "") or "").strip()
    to_scene = str(getattr(args, "to_scene", "") or "").strip()
    if not from_scene or not to_scene:
        print("[Mesh][CLI] Error: missing --from-scene/--to-scene")
        return 2

    from_x = float(getattr(args, "from_x"))
    from_y = float(getattr(args, "from_y"))
    to_x = float(getattr(args, "to_x"))
    to_y = float(getattr(args, "to_y"))

    from_spawn = str(getattr(args, "from_spawn", "") or "").strip()
    to_spawn = str(getattr(args, "to_spawn", "") or "").strip()
    if not from_spawn or not to_spawn:
        print("[Mesh][CLI] Error: missing --from-spawn/--to-spawn")
        return 2

    bidirectional = bool(getattr(args, "bidirectional", False))

    resolved_world = resolve_path(world_path)
    if not resolved_world.exists():
        print(f"[Mesh][CLI] Error: world not found: {normalize_scene_path(world_path)}")
        return 1

    try:
        world_payload = json.loads(resolved_world.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # REASON: world CLI should report world JSON parse failures deterministically before inspecting scene mappings
        print(f"[Mesh][CLI] Error: failed to parse world JSON: {normalize_scene_path(world_path)}: {exc}")
        return 1
    if not isinstance(world_payload, dict):
        print(f"[Mesh][CLI] Error: world JSON root must be an object: {normalize_scene_path(world_path)}")
        return 1

    scenes_map = world_payload.get("scenes")
    if not isinstance(scenes_map, dict):
        print(f"[Mesh][CLI] Error: world.scenes must be an object: {normalize_scene_path(world_path)}")
        return 1

    def world_path_for_key(key: str) -> str | None:
        entry = scenes_map.get(key)
        if not isinstance(entry, dict):
            return None
        raw = entry.get("path")
        return normalize_scene_path(str(raw)) if isinstance(raw, str) and raw.strip() else None

    expected_from = normalize_scene_path(from_scene)
    expected_to = normalize_scene_path(to_scene)
    actual_from = world_path_for_key(from_key)
    actual_to = world_path_for_key(to_key)
    if actual_from is None:
        print(f"[Mesh][CLI] Error: world missing scene key: {from_key!r} (use `python -m mesh_cli world add-scene ...`)")
        return 1
    if actual_to is None:
        print(f"[Mesh][CLI] Error: world missing scene key: {to_key!r} (use `python -m mesh_cli world add-scene ...`)")
        return 1
    if actual_from != expected_from:
        print(f"[Mesh][CLI] Error: world scene path mismatch for {from_key!r}: world={actual_from} args={expected_from}")
        return 1
    if actual_to != expected_to:
        print(f"[Mesh][CLI] Error: world scene path mismatch for {to_key!r}: world={actual_to} args={expected_to}")
        return 1

    loader = SceneLoader()

    def load_scene(scene_path: str) -> tuple[Path, dict] | None:
        resolved_scene = resolve_path(scene_path)
        if not resolved_scene.exists():
            print(f"[Mesh][CLI] Error: scene not found: {normalize_scene_path(scene_path)}")
            return None
        try:
            raw_scene = json.loads(resolved_scene.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # REASON: world CLI should report scene JSON parse failures deterministically before applying scene defaults
            print(f"[Mesh][CLI] Error: failed to parse scene JSON: {normalize_scene_path(scene_path)}: {exc}")
            return None
        if not isinstance(raw_scene, dict):
            print(f"[Mesh][CLI] Error: scene JSON root must be an object: {normalize_scene_path(scene_path)}")
            return None
        return resolved_scene, loader.apply_scene_defaults(raw_scene)

    from_loaded = load_scene(from_scene)
    if from_loaded is None:
        return 1
    to_loaded = load_scene(to_scene)
    if to_loaded is None:
        return 1

    from_path, from_payload = from_loaded
    to_path, to_payload = to_loaded

    from_entities = from_payload.get("entities")
    if from_entities is None:
        from_entities = []
        from_payload["entities"] = from_entities
    if not isinstance(from_entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {normalize_scene_path(from_scene)}")
        return 1

    to_entities = to_payload.get("entities")
    if to_entities is None:
        to_entities = []
        to_payload["entities"] = to_entities
    if not isinstance(to_entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {normalize_scene_path(to_scene)}")
        return 1

    # Use scene_commands helper for ID generation to match legacy behavior
    from_entity_id = scene_commands._default_transition_entity_id(from_scene, to_key, from_x, from_y)
    changed_from, error = _ensure_scene_transition_entity(
        entities=from_entities,
        entity_id=from_entity_id,
        target_scene=to_key,
        spawn_id=to_spawn,
        x=from_x,
        y=from_y,
        name=f"TransitionTo_{to_key}",
    )
    if error:
        print(f"[Mesh][CLI] Error: {normalize_scene_path(from_scene)}: {error}")
        return 1

    changed_to = False
    if bidirectional:
        to_entity_id = scene_commands._default_transition_entity_id(to_scene, from_key, to_x, to_y)
        changed_to, error = _ensure_scene_transition_entity(
            entities=to_entities,
            entity_id=to_entity_id,
            target_scene=from_key,
            spawn_id=from_spawn,
            x=to_x,
            y=to_y,
            name=f"TransitionTo_{from_key}",
        )
        if error:
            print(f"[Mesh][CLI] Error: {normalize_scene_path(to_scene)}: {error}")
            return 1

    if not changed_from and not changed_to:
        return 0

    def validate_and_write(resolved_scene: Path, payload: dict, display: str) -> int:
        report = loader.validate_scene(payload, strict=False)
        if report.errors:
            for msg in report.errors:
                print(f"[Mesh][CLI] Error: {normalize_scene_path(display)}: {msg}")
            return 1
        compacted = compact_scene_payload(payload)
        write_json_atomic(resolved_scene, compacted, indent=2, sort_keys=True, trailing_newline=True)
        return 0

    if changed_from:
        rc = validate_and_write(from_path, from_payload, from_scene)
        if rc != 0:
            return rc
    if changed_to:
        rc = validate_and_write(to_path, to_payload, to_scene)
        if rc != 0:
            return rc

    return 0


def _handle_world_graph(args: argparse.Namespace) -> int:
    """Export world graph to DOT format."""
    return 0 if graph.export_graph(args.world_path, args.output) else 1


def _handle_auto_wire_transitions(args: argparse.Namespace) -> int:
    """Run the auto-wire transitions tool."""
    controller = AutoWireController(args.world_path)
    try:
        controller.load()
        changes = controller.process(dry_run=not args.apply)
        for change in changes:
            print(f"[AutoWire] {change}")
        if not changes:
            print("[AutoWire] No changes needed.")
        elif args.apply:
            print(f"[AutoWire] Applied {len(changes)} changes.")
        else:
            print(f"[AutoWire] Found {len(changes)} changes (dry-run). Use --apply to save.")
        return 1
    except Exception as e:
        print(f"[AutoWire] Error: {e}")
        return 1


def register(subparsers: argparse._SubParsersAction) -> None:
    # World authoring
    world_parser = subparsers.add_parser(
        "world",
        help="World authoring utilities",
        description="World authoring utilities",
    )
    world_subparsers = world_parser.add_subparsers(dest="world_command", help="World subcommand")

    world_add_scene = world_subparsers.add_parser(
        "add-scene",
        help="Add or update a scene entry in a world file",
        description="Add or update a scene entry in a world file",
    )
    world_add_scene.add_argument("world_path", help="Path to world file")
    world_add_scene.add_argument("--key", required=True, help="Scene key to add/update")
    world_add_scene.add_argument("--path", required=True, help="Scene JSON path (stored with forward slashes)")

    world_link_scenes = world_subparsers.add_parser(
        "link-scenes",
        help="Insert SceneTransition entities linking two scenes (idempotent; validates after edit)",
        description="Insert SceneTransition entities linking two scenes (idempotent; validates after edit)",
    )
    world_link_scenes.add_argument("world_path", help="Path to world file")
    world_link_scenes.add_argument("--from-key", required=True, dest="from_key", help="World scene key for the source scene")
    world_link_scenes.add_argument("--to-key", required=True, dest="to_key", help="World scene key for the destination scene")
    world_link_scenes.add_argument("--from-scene", required=True, dest="from_scene", help="Source scene JSON path")
    world_link_scenes.add_argument("--to-scene", required=True, dest="to_scene", help="Destination scene JSON path")
    world_link_scenes.add_argument("--from-x", required=True, dest="from_x", type=float, help="Source transition X")
    world_link_scenes.add_argument("--from-y", required=True, dest="from_y", type=float, help="Source transition Y")
    world_link_scenes.add_argument("--to-x", required=True, dest="to_x", type=float, help="Destination transition X")
    world_link_scenes.add_argument("--to-y", required=True, dest="to_y", type=float, help="Destination transition Y")
    world_link_scenes.add_argument("--from-spawn", required=True, dest="from_spawn", help="Spawn id to use when traveling to the source scene")
    world_link_scenes.add_argument("--to-spawn", required=True, dest="to_spawn", help="Spawn id to use when traveling to the destination scene")
    world_link_scenes.add_argument("--bidirectional", action="store_true", help="Also add reverse transition entity")

    # Validate World
    validate_world_parser = subparsers.add_parser(
        "validate-world",
        help="Validate world structure",
        description="Validate world structure",
    )
    validate_world_parser.add_argument("world_path", help="Path to world file")
    validate_world_parser.add_argument("--no-events", action="store_true", help="Skip event validation")

    # Auto Wire
    auto_wire_parser = subparsers.add_parser(
        "auto-wire-transitions",
        help="Auto-wire scene transitions",
        description="Auto-wire scene transitions",
    )
    auto_wire_parser.add_argument("world_path", help="World file")
    auto_wire_parser.add_argument("--apply", action="store_true", help="Apply changes")

    # World Graph
    graph_parser = subparsers.add_parser(
        "world-graph",
        help="Export world graph",
        description="Export world graph",
    )
    graph_parser.add_argument("world_path", help="World file")
    graph_parser.add_argument("output", help="Output DOT file")


def handle(args: argparse.Namespace) -> int:
    if args.command == "world":
        if getattr(args, "world_command", None) == "add-scene":
            return _handle_world_add_scene(args)
        if getattr(args, "world_command", None) == "link-scenes":
            return _handle_world_link_scenes(args)
        print("[Mesh][CLI] Error: missing world subcommand")
        return 2
    
    if args.command == "validate-world":
        return _handle_validate_world(args)
    
    if args.command == "auto-wire-transitions":
        return _handle_auto_wire_transitions(args)
    
    if args.command == "world-graph":
        return _handle_world_graph(args)

    return 1
