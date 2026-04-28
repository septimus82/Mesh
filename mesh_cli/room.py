from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.swallowed_exceptions import _log_swallow

def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # Room scaffolding
    room_parser = subparsers.add_parser("room", help="Room scaffolding utilities")
    room_subparsers = room_parser.add_subparsers(dest="room_command", help="Room subcommand")
    room_scaffold = room_subparsers.add_parser(
        "scaffold",
        help="Create a new room scene and link it from an existing scene (idempotent)",
    )
    room_scaffold.add_argument("--world", required=True, help="Path to world file")
    room_scaffold.add_argument("--from-scene", required=True, dest="from_scene", help="Source scene JSON path")
    room_scaffold.add_argument("--door-macro", required=True, dest="door_macro", help="Macro asset to apply to from-scene")
    room_scaffold.add_argument("--to-scene", required=True, dest="to_scene", help="New scene JSON path")
    room_scaffold.add_argument("--to-stamp", required=True, dest="to_stamp", help="Stamp JSON path to apply into to-scene")
    room_scaffold.add_argument("--grid", required=True, help="Scene grid dims as WxH (tile coords)")
    room_scaffold.add_argument("--tile", required=True, help="Tile size as WxH (world units)")
    room_scaffold.add_argument("--layers", required=True, help="Comma-separated layer specs: id:z[:parallax],...")
    room_scaffold.add_argument("--collision-layer", dest="collision_layer", help="Optional collision layer id")
    room_scaffold.add_argument("--stamp-origin", dest="stamp_origin", help="Optional stamp origin as x,y (tile coords)")
    room_scaffold.add_argument("--spawn-id", dest="spawn_id", help="Spawn id to create/use in the new scene")
    room_scaffold.add_argument("--anchor", choices=["primary", "cursor", "player"], default="player", help="Anchor mode for macro placement")
    room_scaffold.add_argument("--id-prefix", dest="id_prefix", help="Optional id prefix override for stamped entities")
    room_scaffold.add_argument("--arg", action="append", default=[], help="Macro arg override k=v (repeatable)")


def handle(args: argparse.Namespace) -> int:
    if getattr(args, "room_command", None) == "scaffold":
        return _handle_room_scaffold(args)
    print("[Mesh][CLI] Error: missing room subcommand")
    return 2


def _handle_room_scaffold(args: argparse.Namespace) -> int:
    """Create a new room scene and wire it into a world using existing authoring primitives."""
    from engine.macro_specs import get_builtin_macro_spec
    from engine.path_norm import normalize_scene_path
    from engine.paths import resolve_path
    from engine.persistence_io import write_json_atomic
    from engine.scene_loader import SceneLoader
    from engine.scene_serializer import compact_scene_payload
    from engine.tooling_runtime.macro_assets import load_macro_asset, parse_macro_asset, validate_macro_asset

    from . import scene as scene_commands
    from . import legacy_impl as legacy_mod

    def parse_pair(spec: str, *, sep: str, label: str) -> tuple[int, int] | None:
        text = str(spec or "").strip().lower()
        if sep not in text:
            print(f"[Mesh][CLI] Error: invalid {label}: {spec!r} (expected a{sep}b)")
            return None
        a, b = text.split(sep, 1)
        try:
            x = int(a)
            y = int(b)
        except (TypeError, ValueError):
            _log_swallow("ROOM-002", "grid/tile pair parse fallback", once=True)
            print(f"[Mesh][CLI] Error: invalid {label}: {spec!r} (expected ints)")
            return None
        if x <= 0 or y <= 0:
            print(f"[Mesh][CLI] Error: invalid {label}: {spec!r} (expected > 0)")
            return None
        return x, y

    def parse_origin(spec: str | None) -> tuple[int, int] | None:
        if spec is None:
            return None
        text = str(spec or "").strip()
        if not text:
            return None
        if "," not in text:
            print(f"[Mesh][CLI] Error: invalid --stamp-origin: {spec!r} (expected x,y)")
            return None
        a, b = text.split(",", 1)
        try:
            return int(a.strip()), int(b.strip())
        except (TypeError, ValueError):
            _log_swallow("ROOM-003", "stamp origin parse fallback", once=True)
            print(f"[Mesh][CLI] Error: invalid --stamp-origin: {spec!r} (expected ints)")
            return None

    def parse_layers_csv(spec: str) -> list[str] | None:
        text = str(spec or "").strip()
        if not text:
            print("[Mesh][CLI] Error: missing --layers")
            return None
        items = [s.strip() for s in text.split(",") if s.strip()]
        if not items:
            print("[Mesh][CLI] Error: missing --layers")
            return None
        return items

    world_path = str(getattr(args, "world", "") or "").strip()
    from_scene = str(getattr(args, "from_scene", "") or "").strip()
    to_scene = str(getattr(args, "to_scene", "") or "").strip()
    stamp_path = str(getattr(args, "to_stamp", "") or "").strip()
    door_macro = str(getattr(args, "door_macro", "") or "").strip()
    if not (world_path and from_scene and to_scene and stamp_path and door_macro):
        print("[Mesh][CLI] Error: missing required args (world/from-scene/to-scene/to-stamp/door-macro)")
        return 2

    grid_spec = parse_pair(str(getattr(args, "grid", "") or ""), sep="x", label="--grid")
    tile_spec = parse_pair(str(getattr(args, "tile", "") or ""), sep="x", label="--tile")
    layers_list = parse_layers_csv(str(getattr(args, "layers", "") or ""))
    if grid_spec is None or tile_spec is None or layers_list is None:
        return 2
    grid_w, grid_h = grid_spec
    tile_w, tile_h = tile_spec

    collision_layer = getattr(args, "collision_layer", None)
    collision_layer_id = str(collision_layer).strip() if isinstance(collision_layer, str) and str(collision_layer).strip() else None

    stamp_origin = parse_origin(getattr(args, "stamp_origin", None))
    origin_x, origin_y = stamp_origin if stamp_origin is not None else (0, 0)

    to_spawn_id = str(getattr(args, "spawn_id", "") or "").strip() or "default"
    # Place spawn at (origin+1,origin+1) tile center (clamped into grid).
    spawn_tx = min(max(origin_x + 1, 0), grid_w - 1)
    spawn_ty = min(max(origin_y + 1, 0), grid_h - 1)
    to_spawn_x = (spawn_tx + 0.5) * float(tile_w)
    to_spawn_y = (spawn_ty + 0.5) * float(tile_h)

    anchor = getattr(args, "anchor", None)
    anchor_override = str(anchor).strip().lower() if isinstance(anchor, str) and str(anchor).strip() else "player"

    id_prefix = str(getattr(args, "id_prefix", "") or "").strip() or None

    raw_user_args = getattr(args, "arg", None)
    raw_user_args = raw_user_args if isinstance(raw_user_args, list) else []

    resolved_world = resolve_path(world_path)
    if not resolved_world.exists():
        print(f"[Mesh][CLI] Error: world not found: {normalize_scene_path(world_path)}")
        return 1

    try:
        world_payload = json.loads(resolved_world.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _log_swallow("ROOM-004", "world JSON parse failure", once=True)
        print(f"[Mesh][CLI] Error: failed to parse world JSON: {normalize_scene_path(world_path)}: {exc}")
        return 1
    if not isinstance(world_payload, dict):
        print(f"[Mesh][CLI] Error: world JSON root must be an object: {normalize_scene_path(world_path)}")
        return 1

    scenes_map = world_payload.get("scenes")
    if scenes_map is None:
        scenes_map = {}
        world_payload["scenes"] = scenes_map
    if not isinstance(scenes_map, dict):
        print(f"[Mesh][CLI] Error: world.scenes must be an object: {normalize_scene_path(world_path)}")
        return 1

    def _world_key_for_path(scene_path: str) -> str:
        wanted = normalize_scene_path(scene_path)
        for k, v in scenes_map.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            raw = v.get("path")
            if isinstance(raw, str) and normalize_scene_path(raw) == wanted:
                return k
        base = Path(scene_path).stem or "scene"
        candidate = base
        i = 2
        while candidate in scenes_map:
            candidate = f"{base}_{i}"
            i += 1
        return candidate

    from_key = _world_key_for_path(from_scene)
    to_key = _world_key_for_path(to_scene)

    def _spawn_points(scene_payload: dict[str, Any]) -> dict[str, tuple[float, float]]:
        out: dict[str, tuple[float, float]] = {}
        entities = scene_payload.get("entities")
        if not isinstance(entities, list):
            return out
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            if str(ent.get("tag") or "") != "spawn_point":
                continue
            sid = ent.get("spawn_id")
            if not isinstance(sid, str) or not sid.strip():
                continue
            try:
                out[sid.strip()] = (float(ent.get("x", 0.0)), float(ent.get("y", 0.0)))
            except (TypeError, ValueError):
                _log_swallow("ROOM-001", "spawn coord parse", once=True)
                out[sid.strip()] = (0.0, 0.0)
        return out

    def _read_scene_payload(scene_path: str) -> dict[str, Any] | None:
        resolved = resolve_path(scene_path)
        if not resolved.exists():
            print(f"[Mesh][CLI] Error: scene not found: {normalize_scene_path(scene_path)}")
            return None
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _log_swallow("ROOM-005", "scene JSON parse failure", once=True)
            print(f"[Mesh][CLI] Error: failed to parse scene JSON: {normalize_scene_path(scene_path)}: {exc}")
            return None
        if not isinstance(payload, dict):
            print(f"[Mesh][CLI] Error: scene JSON root must be an object: {normalize_scene_path(scene_path)}")
            return None
        return payload

    from_scene_payload = _read_scene_payload(from_scene)
    if from_scene_payload is None:
        return 1
    from_spawns = _spawn_points(from_scene_payload)
    start_scene = str(world_payload.get("start_scene") or "").strip()
    start_spawn = str(world_payload.get("start_spawn") or "").strip()
    if start_scene and start_scene == from_key and start_spawn and start_spawn in from_spawns:
        from_spawn_id = start_spawn
    elif "default" in from_spawns:
        from_spawn_id = "default"
    elif from_spawns:
        from_spawn_id = sorted(from_spawns.keys())[0]
    else:
        from_spawn_id = "default"
    from_x, from_y = from_spawns.get(from_spawn_id, (0.0, 0.0))

    # Load door macro spec for strict arg handling.
    try:
        macro_payload = load_macro_asset(door_macro)
        issues = validate_macro_asset(macro_payload, rel_path=normalize_scene_path(door_macro))
        if issues:
            first = issues[0]
            print(f"[Mesh][CLI] Error: {first.path} :: {first.code} :: {first.detail}")
            return 1
        macro_asset = parse_macro_asset(macro_payload, rel_path=normalize_scene_path(door_macro))
    except Exception as exc:  # noqa: BLE001  # REASON: room CLI should collapse macro asset load and validation failures into a deterministic door-macro error
        _log_swallow("ROOM-006", "door macro load failure", once=True)
        print(f"[Mesh][CLI] Error: failed to load macro asset: {normalize_scene_path(door_macro)}: {exc}")
        return 1

    macro_id = str(macro_asset.macro_id or "").strip()
    spec = get_builtin_macro_spec(macro_id)
    if spec is None:
        print(f"[Mesh][CLI] Error: unknown macro_id: {macro_id!r}")
        return 1

    def _parse_kv(raw_list: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for raw in raw_list:
            text = str(raw or "").strip()
            if not text:
                continue
            if "=" not in text:
                raise ValueError(f"bad_arg {text!r} (expected k=v)")
            k, v = text.split("=", 1)
            k = k.strip()
            if not k:
                raise ValueError(f"bad_arg {text!r} (empty key)")
            out[k] = v
        return out

    try:
        user_kv = _parse_kv(raw_user_args)
    except ValueError as exc:
        _log_swallow("ROOM-007", "macro arg parse failure", once=True)
        print(f"[Mesh][CLI] Error: {exc}")
        return 2

    # Track writes (unique files whose contents changed at least once).
    tracked_paths: dict[str, Path] = {
        "world": resolved_world,
        "from_scene": resolve_path(from_scene),
        "to_scene": resolve_path(to_scene),
    }
    snapshots: dict[str, bytes | None] = {k: (p.read_bytes() if p.exists() else None) for k, p in tracked_paths.items()}
    wrote_files: set[str] = set()

    def _note_changes() -> None:
        for label, path in tracked_paths.items():
            before = snapshots[label]
            after = path.read_bytes() if path.exists() else None
            if after != before:
                wrote_files.add(normalize_scene_path(str(path)))
                snapshots[label] = after

    created_scene = False

    # 1) Ensure to-scene exists (strict no-overwrite: only create if missing).
    if not tracked_paths["to_scene"].exists():
        created_scene = True
        create_ns = argparse.Namespace(
            scene_path=to_scene,
            width=grid_w,
            height=grid_h,
            tile_w=tile_w,
            tile_h=tile_h,
            layer=layers_list,
            collision_layer=collision_layer_id,
            bg=[],
            spawn=[f"{to_spawn_id}:{to_spawn_x:g}:{to_spawn_y:g}"],
        )
        rc: int = scene_commands._handle_scene_create(create_ns)
        if rc != 0:
            return rc
        _note_changes()

    # 2) Ensure tilemap dims/layers.
    init_ns = argparse.Namespace(
        scene_path=to_scene,
        width=grid_w,
        height=grid_h,
        tile_w=tile_w,
        tile_h=tile_h,
        layer=layers_list,
        collision_layer=collision_layer_id,
        fill=[],
    )
    rc = scene_commands._handle_scene_tilemap_init(init_ns)
    if rc != 0:
        return rc
    _note_changes()

    # 3) Apply stamp into to-scene.
    stamp_ns = argparse.Namespace(
        scene_path=to_scene,
        stamp=stamp_path,
        x=int(origin_x),
        y=int(origin_y),
        id_prefix=id_prefix,
    )
    rc = scene_commands._handle_scene_stamp(stamp_ns)
    if rc != 0:
        return rc
    _note_changes()

    # 4) Add both scenes into the world (idempotent).
    add_from_ns = argparse.Namespace(world_path=world_path, key=from_key, path=from_scene)
    rc = legacy_mod._handle_world_add_scene(add_from_ns)
    if rc != 0:
        return rc
    _note_changes()
    add_to_ns = argparse.Namespace(world_path=world_path, key=to_key, path=to_scene)
    rc = legacy_mod._handle_world_add_scene(add_to_ns)
    if rc != 0:
        return rc
    _note_changes()

    # 5) Link scenes (bidirectional) via SceneTransition entities.
    link_ns = argparse.Namespace(
        world_path=world_path,
        from_key=from_key,
        to_key=to_key,
        from_scene=from_scene,
        to_scene=to_scene,
        from_x=float(from_x),
        from_y=float(from_y),
        to_x=float(to_spawn_x),
        to_y=float(to_spawn_y),
        from_spawn=from_spawn_id,
        to_spawn=to_spawn_id,
        bidirectional=True,
    )
    rc = legacy_mod._handle_world_link_scenes(link_ns)
    if rc != 0:
        return rc
    _note_changes()

    # 6) Apply door macro into from-scene (idempotent).
    macro_created = 0
    macro_updated = 0

    raw_args = list(raw_user_args)
    primary_entity_id: str | None = None

    if macro_id == "macro.door_transition":
        # Keep idempotency with world link-scenes by enforcing target_scene/to_spawn agreement.
        if "target_scene" in user_kv and str(user_kv.get("target_scene") or "").strip() != to_key:
            print(f"[Mesh][CLI] Error: --arg target_scene must equal world key {to_key!r} for idempotency")
            return 1
        if "spawn_id" in user_kv and str(user_kv.get("spawn_id") or "").strip() != to_spawn_id:
            print(f"[Mesh][CLI] Error: --arg spawn_id must equal {to_spawn_id!r} for idempotency")
            return 1

        if "target_scene" not in user_kv:
            raw_args.append(f"target_scene={to_key}")
        if "spawn_id" not in user_kv:
            raw_args.append(f"spawn_id={to_spawn_id}")

        primary_entity_id = scene_commands._default_transition_entity_id(from_scene, to_key, float(from_x), float(from_y))

    resolved_from = resolve_path(from_scene)
    before_payload = json.loads(resolved_from.read_text(encoding="utf-8"))
    if not isinstance(before_payload, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {normalize_scene_path(from_scene)}")
        return 1

    try:
        after_payload, report_payload = scene_commands._compute_scene_macro_apply(
            scene_payload=before_payload,
            scene_path=from_scene,
            macro_path=door_macro,
            raw_args=raw_args,
            anchor_override=anchor_override,
            primary_entity_id=primary_entity_id,
            cursor_world_pos=(float(from_x), float(from_y)),
        )
    except Exception as exc:  # noqa: BLE001  # REASON: room CLI should collapse unexpected macro application failures into a deterministic nonzero exit
        _log_swallow("ROOM-008", "scene macro apply failure", once=True)
        print(f"[Mesh][CLI] Error: macro-apply failed: {type(exc).__name__}: {exc}")
        return 1

    if after_payload != before_payload:
        loader = SceneLoader()
        full_scene = loader.apply_scene_defaults(after_payload)
        report = loader.validate_scene(full_scene, strict=False)
        if not report.ok:
            print(f"[Mesh][CLI] Error: scene validation failed after macro apply: {normalize_scene_path(from_scene)}")
            for msg in report.errors:
                print(f"[Mesh][CLI] ERROR: {msg}")
            return 1
        compacted = compact_scene_payload(full_scene)
        write_json_atomic(resolved_from, compacted, indent=2, sort_keys=False, trailing_newline=True)
        _note_changes()

    macro_created = int(report_payload.get("will_create") or 0) if isinstance(report_payload, dict) else 0
    macro_updated = int(report_payload.get("will_update") or 0) if isinstance(report_payload, dict) else 0

    if not wrote_files:
        print("ROOM_SCAFFOLD noop reason=no_changes")
        return 0

    print(
        f"ROOM_SCAFFOLD ok created_scene={'y' if created_scene else 'n'} wrote={len(wrote_files)} "
        f"macros_created={macro_created} macros_updated={macro_updated}",
    )
    return 0
