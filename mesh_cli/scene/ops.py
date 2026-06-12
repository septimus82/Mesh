import argparse
import json
import os
import sys
from pathlib import Path

from engine.logging_tools import suppress_stdout
from engine.persistence_io import dumps_json_deterministic, write_json_atomic
from engine.repo_root import get_repo_root
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.swallowed_exceptions import _log_swallow
from engine.tooling import project_index, scaffold, scene_validate
from engine.tooling.content_inventory import list_scenes
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Action, Plan
from mesh_cli.scene.common import _single_line_error


def _emit_inventory(payload: dict, out_path: str | None) -> int:
    text = dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True)
    if out_path:
        write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(text.encode("utf-8"))
    else:
        sys.stdout.write(text)
    return 0


def _handle_new_scene(args: argparse.Namespace) -> int:
    """Create a new scene file."""
    name = args.name
    if not name.endswith(".json"):
        name += ".json"

    # If no directory specified, default to scenes/
    if os.path.sep not in name and "/" not in name:
        name = os.path.join("scenes", name)

    try:
        extra_args = {}
        if hasattr(args, "encounter_layout") and args.encounter_layout:
            extra_args["encounter_layout"] = args.encounter_layout

        scaffold.create_scene(name, args.template, extra_args=extra_args)
        print(f"[Mesh][CLI] Created scene '{name}' using template '{args.template}'")
        # Re-index to include the new file
        project_index.main([])
        return 0
    except Exception as e:
        _log_swallow("SOPS-001", "new scene scaffold failure", once=True)
        print(f"[Mesh][CLI] Error creating scene: {e}")
        return 1


def _handle_edit_scene(args: argparse.Namespace) -> int:
    """Handle edit-scene command by constructing and executing a plan."""
    actions = []

    # Handle encounter settings
    if args.budget is not None or args.elite_cap is not None or args.allow_elites is not None or args.boss_reserve is not None:
        update_args = {"scene_path": args.path}
        if args.budget is not None:
            update_args["encounter_budget"] = args.budget
        if args.elite_cap is not None:
            update_args["max_elites"] = args.elite_cap
        if args.allow_elites is not None:
            update_args["allow_elites"] = (args.allow_elites == "true")
        if args.boss_reserve is not None:
            update_args["boss_reserve"] = args.boss_reserve

        actions.append(Action(type="update_scene_settings", args=update_args, description="Update scene encounter settings"))

    # Handle add transition
    if args.add_transition:
        x, y = 0, 0
        if args.at:
            try:
                x, y = map(int, args.at.split(","))
            except ValueError:
                print("Error: --at must be in format x,y")
                return 1

        actions.append(Action(type="add_transition", args={
            "scene_path": args.path,
            "target_scene": args.add_transition,
            "x": x,
            "y": y,
            "spawn_id": args.spawn_id or "default"
        }, description=f"Add transition to {args.add_transition}"))

    if not actions:
        print("No changes specified.")
        return 1

    plan = Plan(
        wizard="edit-scene",
        version=1,
        inputs={"path": args.path},
        actions=actions
    )
    executor = PlanExecutor()

    try:
        executor.execute(plan)
        print(f"Successfully updated {args.path}")
        return 0
    except Exception as e:
        _log_swallow("SOPS-002", "edit scene plan execution failure", once=True)
        print(f"Error executing plan: {e}")
        return 1


def _handle_tidy_scene(args: argparse.Namespace) -> int:
    """Load, apply defaults, compact, and save a scene."""
    path = args.scene_path
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        loader = SceneLoader()
        full_scene = loader.apply_scene_defaults(data)
        compacted = compact_scene_payload(full_scene)

        write_json_atomic(Path(path), compacted)

        print(f"[Mesh][CLI] Tidied scene '{path}'")
        return 0
    except Exception as e:
        _log_swallow("SOPS-003", "tidy scene failure", once=True)
        print(f"[Mesh][CLI] Error tidying scene: {e}")
        return 1


def _handle_list_scenes(args: argparse.Namespace) -> int:
    try:
        with suppress_stdout():
            repo_root = get_repo_root(start=Path.cwd(), strict=True)
            payload = list_scenes(repo_root=repo_root)
    except Exception as exc:  # noqa: BLE001  # REASON: scene inventory CLI should collapse unexpected repository scan failures into a deterministic error payload
        _log_swallow("SOPS-004", "list scenes inventory fallback", once=True)
        payload = {"ok": False, "error": _single_line_error(f"{type(exc).__name__}: {exc}")}
    out_path = str(getattr(args, "out", "") or "").strip() or None
    return _emit_inventory(payload, out_path)


def _handle_validate_scene_file(args: argparse.Namespace) -> int:
    """Run the scene validator."""
    # Reconstruct argv for the tool's main function
    tool_argv = [args.scene_path]
    return scene_validate.main(tool_argv)


def _handle_scene_create(args: argparse.Namespace) -> int:
    """Create (or update) a scene JSON with a multi-layer tilemap and optional backgrounds/spawns."""
    from engine.paths import resolve_path
    from mesh_cli.scene.entities import _default_spawn_entity_id
    from mesh_cli.scene.tilemap import _parse_tilemap_layer_spec

    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    width = int(getattr(args, "width"))
    height = int(getattr(args, "height"))
    tile_w = int(getattr(args, "tile_w"))
    tile_h = int(getattr(args, "tile_h"))
    if width <= 0 or height <= 0 or tile_w <= 0 or tile_h <= 0:
        print("[Mesh][CLI] Error: dimensions must be positive")
        return 2

    layer_specs = list(getattr(args, "layer", []) or [])
    parsed_layers: list[dict] = []
    for spec in layer_specs:
        parsed = _parse_tilemap_layer_spec(str(spec))
        if not isinstance(parsed, dict):
            print(f"[Mesh][CLI] Error: invalid layer spec: {spec}")
            return 2
        if not isinstance(parsed.get("id"), str) or not parsed["id"]:
            print(f"[Mesh][CLI] Error: invalid layer spec: {spec}")
            return 2
        parsed_layers.append(parsed)

    collision_layer_id = getattr(args, "collision_layer", None)
    if collision_layer_id is not None:
        collision_layer_id = str(collision_layer_id).strip() or None

    bg_specs = list(getattr(args, "bg", []) or [])
    spawn_specs = list(getattr(args, "spawn", []) or [])

    resolved = resolve_path(scene_path)
    if resolved.exists():
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # REASON: scene create CLI should report scene JSON parse failures deterministically before mutating an existing scene
            _log_swallow("SOPS-005", "scene create JSON parse failure", once=True)
            print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
            return 1
        if not isinstance(data, dict):
            print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
            return 1
    else:
        data = {"entities": []}

    entities = data.get("entities")
    if entities is None:
        entities = []
        data["entities"] = entities
    if not isinstance(entities, list):
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {scene_path}")
        return 1

    tilemap = data.get("tilemap")
    if tilemap is None:
        tilemap = {}
        data["tilemap"] = tilemap
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: scene.tilemap must be an object: {scene_path}")
        return 1

    existing_w = tilemap.get("width")
    existing_h = tilemap.get("height")
    if isinstance(existing_w, int) and isinstance(existing_h, int):
        if (existing_w, existing_h) != (width, height):
            if isinstance(tilemap.get("tile_layers"), list):
                print("[Mesh][CLI] Error: scene tilemap dims mismatch; use `scene tilemap resize` instead")
                return 1

    tilemap["width"] = width
    tilemap["height"] = height
    tilemap["tilewidth"] = tile_w
    tilemap["tileheight"] = tile_h
    if collision_layer_id is not None:
        tilemap["collision_layer_id"] = collision_layer_id

    layers = tilemap.get("tile_layers")
    if layers is None:
        layers = []
        tilemap["tile_layers"] = layers
    if not isinstance(layers, list):
        print(f"[Mesh][CLI] Error: tilemap.tile_layers must be a list: {scene_path}")
        return 1

    wanted_ids = [str(L["id"]) for L in parsed_layers]
    wanted_set = set(wanted_ids)

    existing_by_id: dict[str, dict] = {}
    trailing: list[dict] = []
    for entry in layers:
        if not isinstance(entry, dict):
            continue
        layer_id = entry.get("id")
        if not isinstance(layer_id, str) or not layer_id:
            trailing.append(entry)
            continue
        if layer_id in existing_by_id:
            trailing.append(entry)
            continue
        existing_by_id[layer_id] = entry
        if layer_id not in wanted_set:
            trailing.append(entry)

    new_layers: list[dict] = []
    for spec in parsed_layers:
        layer_id = str(spec["id"])
        layer_z = int(spec.get("z", 0))
        layer_parallax = float(spec.get("parallax", 1.0))

        existing = existing_by_id.get(layer_id)
        if existing is not None:
            tiles = existing.get("tiles")
            if not isinstance(tiles, list) or len(tiles) != width * height:
                print(f"[Mesh][CLI] Error: existing layer tiles length mismatch: {scene_path} layer={layer_id}")
                return 1
            existing["z"] = layer_z
            existing["parallax"] = layer_parallax
            new_layers.append(existing)
            continue

        new_layers.append({"id": layer_id, "z": layer_z, "parallax": layer_parallax, "tiles": [0] * (width * height)})

    for entry in layers:
        if isinstance(entry, dict) and entry.get("id") not in wanted_set:
            new_layers.append(entry)

    tilemap["tile_layers"] = new_layers

    # Background layers (optional)
    if bg_specs:
        bg_layers = data.get("background_layers")
        if bg_layers is None:
            bg_layers = []
            data["background_layers"] = bg_layers
        if not isinstance(bg_layers, list):
            print(f"[Mesh][CLI] Error: background_layers must be a list: {scene_path}")
            return 1

        bg_existing: dict[str, dict] = {}
        bg_trailing: list[dict] = []
        for entry in bg_layers:
            if not isinstance(entry, dict):
                continue
            lid = entry.get("id")
            if isinstance(lid, str) and lid and lid not in bg_existing:
                bg_existing[lid] = entry
            else:
                bg_trailing.append(entry)

        bg_new: list[dict] = []
        for spec in bg_specs:
            parts = [p.strip() for p in str(spec or "").split(":")]
            if len(parts) < 4:
                print(f"[Mesh][CLI] Error: invalid --bg spec: {spec!r}")
                return 2
            layer_id, path, z_s, parallax_s = parts[0], parts[1], parts[2], parts[3]
            if not layer_id or not path:
                print(f"[Mesh][CLI] Error: invalid --bg spec: {spec!r}")
                return 2
            try:
                z = int(z_s)
                parallax = float(parallax_s)
            except (TypeError, ValueError):
                _log_swallow("SOPS-006", "background spec parse fallback", once=True)
                print(f"[Mesh][CLI] Error: invalid --bg spec: {spec!r}")
                return 2

            repeat_x = False
            repeat_y = False
            if len(parts) > 4:
                repeat_x = str(parts[4]).strip() not in {"0", "false", ""}
            if len(parts) > 5:
                repeat_y = str(parts[5]).strip() not in {"0", "false", ""}

            payload = bg_existing.get(layer_id) or {"id": layer_id}
            payload["id"] = layer_id
            payload["path"] = path
            payload["z"] = z
            payload["parallax"] = parallax
            payload["repeat_x"] = bool(repeat_x)
            payload["repeat_y"] = bool(repeat_y)
            bg_new.append(payload)

        for entry in bg_layers:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"] not in {b["id"] for b in bg_new}:
                bg_new.append(entry)

        data["background_layers"] = bg_new

    # Spawn points (optional)
    for spec in spawn_specs:
        parts = [p.strip() for p in str(spec or "").split(":")]
        if len(parts) != 3:
            print(f"[Mesh][CLI] Error: invalid --spawn spec: {spec!r} (expected spawn_id:x:y)")
            return 2
        spawn_id, x_s, y_s = parts
        if not spawn_id:
            print(f"[Mesh][CLI] Error: invalid --spawn spec: {spec!r} (missing spawn_id)")
            return 2
        try:
            x = float(x_s)
            y = float(y_s)
        except (TypeError, ValueError):
            _log_swallow("SOPS-007", "spawn spec parse fallback", once=True)
            print(f"[Mesh][CLI] Error: invalid --spawn spec: {spec!r} (expected numeric x/y)")
            return 2

        ent_id = _default_spawn_entity_id(scene_path, spawn_id, x, y)
        existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == ent_id), None)
        if existing is None:
            entities.append(
                {
                    "behaviours": [],
                    "id": ent_id,
                    "layer": "background",
                    "name": f"Spawn_{spawn_id}",
                    "spawn_id": spawn_id,
                    "tag": "spawn_point",
                    "x": float(x),
                    "y": float(y),
                }
            )
            continue

        if existing.get("tag") != "spawn_point":
            print(f"[Mesh][CLI] Error: spawn entity id already exists with different tag: {scene_path} id={ent_id}")
            return 1
        existing["spawn_id"] = spawn_id
        existing["x"] = float(x)
        existing["y"] = float(y)

    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(full_scene)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=True, trailing_newline=True)
    return 0
