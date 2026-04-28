import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.path_norm import normalize_scene_path
from engine.tilemap_brush import apply_brush, validate_brush
from engine.tilemap_flood_fill import FloodFillMaxTilesExceeded, apply_flood_fill, flood_fill_indices
from engine.swallowed_exceptions import _log_swallow


class BrushLoader:
    def load_brush(self, path: str) -> dict[str, Any]:
        resolved = resolve_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"brush not found: {path}")
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"failed to parse brush JSON: {path}: {exc}") from exc
        return validate_brush(data)



def _scene_validate_scene_payload(scene_path: str, data: dict) -> int:
    loader = SceneLoader()
    full_scene = loader.apply_scene_defaults(data)
    report = loader.validate_scene(full_scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed: {scene_path}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1
    return 0


def _tilemap_validate_scene_payload(
    scene_path_display: str,
    scene_path: Path,
    scene: dict,
) -> tuple[str, list[tuple[str, str, str, str]]]:
    normalized_scene_path = normalize_scene_path(scene_path_display)
    errors: list[tuple[str, str, str, str]] = []

    if not isinstance(scene, dict):
        return normalized_scene_path, [(normalized_scene_path, "", "scene", "scene payload must be an object")]

    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict):
        return normalized_scene_path, [(normalized_scene_path, "", "tilemap", "tilemap missing or not an object")]

    width: int | None = tilemap.get("width") if isinstance(tilemap.get("width"), int) else None
    height: int | None = tilemap.get("height") if isinstance(tilemap.get("height"), int) else None
    if width is None or height is None or width <= 0 or height <= 0:
        map_path_value = tilemap.get("resolved_path") or tilemap.get("path")
        if isinstance(map_path_value, str) and map_path_value.strip():
            raw_map_path = map_path_value.strip()
            candidate_path = Path(raw_map_path)
            map_candidates: list[Path] = []
            if candidate_path.is_absolute():
                map_candidates.append(candidate_path)
            else:
                map_candidates.append((scene_path.parent / candidate_path).resolve())
                map_candidates.append((Path.cwd() / candidate_path).resolve())

            chosen_map_path = map_candidates[-1] if map_candidates else candidate_path
            for candidate in map_candidates:
                if candidate.exists():
                    chosen_map_path = candidate
                    break

            try:
                tiled = json.loads(chosen_map_path.read_text(encoding="utf-8"))
                width_val = int(tiled.get("width", 0))
                height_val = int(tiled.get("height", 0))
                if width_val > 0 and height_val > 0:
                    width = width_val
                    height = height_val
            except Exception:
                _log_swallow("TILE-015", "mesh_cli/scene/tilemap.py pass-only blanket swallow")
                pass

    if width is None or height is None or width <= 0 or height <= 0:
        return normalized_scene_path, [(normalized_scene_path, "", "dims", "cannot determine tilemap width/height")]

    expected_len = int(width) * int(height)

    layers_value = tilemap.get("tile_layers")
    if layers_value is None:
        return normalized_scene_path, [(normalized_scene_path, "", "tile_layers", "tilemap.tile_layers missing")]
    if not isinstance(layers_value, list):
        return normalized_scene_path, [(normalized_scene_path, "", "tile_layers", "tilemap.tile_layers must be a list")]

    seen: set[tuple[str, str]] = set()
    id_counts: dict[str, int] = {}
    for entry in layers_value:
        if not isinstance(entry, dict):
            continue
        layer_id_raw = entry.get("id")
        if not isinstance(layer_id_raw, str) or not layer_id_raw.strip():
            continue
        layer_id = layer_id_raw.strip()
        id_counts[layer_id] = id_counts.get(layer_id, 0) + 1

    for layer_id, count in id_counts.items():
        if count > 1:
            seen.add((layer_id, "id"))
            errors.append((normalized_scene_path, layer_id, "id", "duplicate layer id"))

    for entry in layers_value:
        if not isinstance(entry, dict):
            continue
        layer_id_raw = entry.get("id")
        layer_id = layer_id_raw.strip() if isinstance(layer_id_raw, str) and layer_id_raw.strip() else ""

        z_value = entry.get("z")
        if not isinstance(z_value, int) and (layer_id, "z") not in seen:
            seen.add((layer_id, "z"))
            errors.append((normalized_scene_path, layer_id, "z", "z must be an int"))

        if "parallax" in entry and (layer_id, "parallax") not in seen:
            parallax_value = entry.get("parallax")
            if not isinstance(parallax_value, (int, float)):
                seen.add((layer_id, "parallax"))
                errors.append((normalized_scene_path, layer_id, "parallax", "parallax must be a number"))
            else:
                parallax = float(parallax_value)
                if parallax < 0.0 or parallax > 2.0:
                    seen.add((layer_id, "parallax"))
                    errors.append((normalized_scene_path, layer_id, "parallax", "parallax must be in [0, 2]"))

        if (layer_id, "tiles") in seen:
            continue
        tiles_value = entry.get("tiles")
        if not isinstance(tiles_value, list):
            seen.add((layer_id, "tiles"))
            errors.append((normalized_scene_path, layer_id, "tiles", "tiles must be a list"))
            continue
        if len(tiles_value) != expected_len:
            seen.add((layer_id, "tiles"))
            errors.append(
                (normalized_scene_path, layer_id, "tiles", f"tiles length must be {expected_len}, got {len(tiles_value)}"),
            )
            continue
        for v in tiles_value:
            if not isinstance(v, int):
                seen.add((layer_id, "tiles"))
                errors.append((normalized_scene_path, layer_id, "tiles", "tiles must contain ints"))
                break

    errors.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return normalized_scene_path, errors


def _parse_tilemap_layer_spec(spec: str) -> dict | None:
    # id:z[:parallax]
    parts = spec.split(":")
    if len(parts) < 2:
        return None
    layer_id = parts[0].strip()
    try:
        z = int(parts[1])
    except ValueError:
        return None
    parallax = 1.0
    if len(parts) > 2:
        try:
            parallax = float(parts[2])
        except ValueError:
            return None
    return {"id": layer_id, "z": z, "parallax": parallax}


def _parse_tilemap_fill_spec(spec: str) -> tuple[str, int] | None:
    # layer_id:tile
    parts = spec.split(":")
    if len(parts) != 2:
        return None
    layer_id = parts[0].strip()
    try:
        tile = int(parts[1])
    except ValueError:
        return None
    return (layer_id, tile)


def _handle_scene_tilemap_add_layer(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    layer_id = str(getattr(args, "id", "") or "").strip()
    if not layer_id:
        print("[Mesh][CLI] Error: missing --id")
        return 2

    z = int(getattr(args, "z"))
    parallax_val = getattr(args, "parallax", None)
    parallax = float(parallax_val) if parallax_val is not None else 1.0
    is_collision = bool(getattr(args, "collision", False))

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-003", f"add_layer: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    if not isinstance(data, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path}")
        return 1

    tilemap = data.get("tilemap")
    if tilemap is None:
        tilemap = {}
        data["tilemap"] = tilemap
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap must be an object: {scene_path}")
        return 1

    _scene_tilemap_maybe_migrate_layers(tilemap)

    layers = tilemap.get("tile_layers")
    if layers is None:
        layers = []
        tilemap["tile_layers"] = layers
    if not isinstance(layers, list):
        print(f"[Mesh][CLI] Error: tilemap.tile_layers must be a list: {scene_path}")
        return 1

    existing = next((L for L in layers if isinstance(L, dict) and L.get("id") == layer_id), None)
    changed = False

    if is_collision and tilemap.get("collision_layer_id") != layer_id:
        tilemap["collision_layer_id"] = layer_id
        changed = True

    if existing is None:
        # Create new
        # We need width/height to init grid if we want to be safe, but usually init handles that.
        # If we just add a layer definition, we might want to init the grid to 0s if width/height exist.
        width = tilemap.get("width", 0)
        height = tilemap.get("height", 0)
        grid = [0] * (width * height)
        new_layer = {
            "id": layer_id,
            "z": z,
            "parallax": parallax,
            "tiles": grid,
        }
        layers.append(new_layer)
        changed = True
    else:
        # Update existing
        if existing.get("z") != z:
            existing["z"] = z
            changed = True
        if existing.get("parallax") != parallax:
            existing["parallax"] = parallax
            changed = True
        if is_collision and not existing.get("collision"):
            existing["collision"] = True
            changed = True
        elif not is_collision and existing.get("collision"):
            del existing["collision"]
            changed = True

    if not changed:
        return 0

    if _scene_validate_scene_payload(scene_path, data) != 0:
        return 1

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_remove_layer(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    layer_id = str(getattr(args, "id", "") or "").strip()
    if not layer_id:
        print("[Mesh][CLI] Error: missing --id")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-004", f"remove_layer: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if not isinstance(tilemap, dict):
        return 0
    layers = tilemap.get("tile_layers")
    if not isinstance(layers, list):
        return 0

    before = len(layers)
    tilemap["tile_layers"] = [L for L in layers if not (isinstance(L, dict) and L.get("id") == layer_id)]
    if len(tilemap["tile_layers"]) == before:
        return 0
    if tilemap.get("collision_layer_id") == layer_id:
        tilemap.pop("collision_layer_id", None)

    if _scene_validate_scene_payload(scene_path, data) != 0:
        return 1

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_init(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    width = int(args.width)
    height = int(args.height)
    tile_w = int(args.tile_w)
    tile_h = int(args.tile_h)
    layer_specs = getattr(args, "layer", []) or []
    collision_layer_id = getattr(args, "collision_layer", None)
    fill_specs = getattr(args, "fill", []) or []

    if width <= 0 or height <= 0 or tile_w <= 0 or tile_h <= 0:
        print("[Mesh][CLI] Error: dimensions must be positive")
        return 2

    parsed_layers = []
    for spec in layer_specs:
        parsed = _parse_tilemap_layer_spec(spec)
        if not parsed:
            print(f"[Mesh][CLI] Error: invalid layer spec: {spec}")
            return 2
        parsed_layers.append(parsed)

    fill_map = {}
    for spec in fill_specs:
        parsed_fill = _parse_tilemap_fill_spec(spec)
        if not parsed_fill:
            print(f"[Mesh][CLI] Error: invalid fill spec: {spec}")
            return 2
        fill_map[parsed_fill[0]] = parsed_fill[1]

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-005", f"init: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if tilemap is None:
        tilemap = {}
        data["tilemap"] = tilemap
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap must be an object: {scene_path}")
        return 1

    existing_w = tilemap.get("width")
    existing_h = tilemap.get("height")
    existing_layers = tilemap.get("tile_layers")
    if (
        isinstance(existing_w, int)
        and isinstance(existing_h, int)
        and isinstance(existing_layers, list)
        and (int(existing_w) > 0 and int(existing_h) > 0)
        and (int(existing_w) != int(width) or int(existing_h) != int(height))
        and any(isinstance(layer, dict) for layer in existing_layers)
    ):
        print("[Mesh][CLI] Error: tilemap dims mismatch; use scene tilemap resize")
        return 1

    # Update dimensions
    tilemap["width"] = width
    tilemap["height"] = height
    tilemap["tilewidth"] = tile_w
    tilemap["tileheight"] = tile_h
    if collision_layer_id:
        tilemap["collision_layer_id"] = str(collision_layer_id)

    layers = tilemap.get("tile_layers")
    if layers is None:
        layers = []
        tilemap["tile_layers"] = layers
    if not isinstance(layers, list):
        print(f"[Mesh][CLI] Error: tilemap.tile_layers must be a list: {scene_path}")
        return 1

    # Ensure all requested layers exist and have correct size
    existing_map = {L.get("id"): L for L in layers if isinstance(L, dict) and L.get("id")}
    
    # Rebuild layers list to preserve order of existing, append new
    # Actually, user might want to enforce order from args? 
    # The command says "Initialize ... (idempotent)". 
    # Let's just ensure they exist.

    for p in parsed_layers:
        lid = p["id"]
        lz = p["z"]
        lpar = p["parallax"]
        
        layer_obj = existing_map.get(lid)
        if layer_obj is None:
            layer_obj = {"id": lid, "z": lz, "parallax": lpar, "tiles": [0] * (width * height)}
            layers.append(layer_obj)
            existing_map[lid] = layer_obj
        
        # Update props
        layer_obj["z"] = lz
        layer_obj["parallax"] = lpar
        
        # Resize tiles if needed
        current_tiles = layer_obj.get("tiles")
        if not isinstance(current_tiles, list) or len(current_tiles) != width * height:
            # Reset to 0s if size mismatch (destructive resize? or just init?)
            # "init" implies setting up. If we want non-destructive resize, use resize command.
            # But let's be safe: if it exists and size differs, we probably should warn or resize safely.
            # For "init", let's just reset to 0s or fill value if provided.
            fill_val = fill_map.get(lid, 0)
            layer_obj["tiles"] = [fill_val] * (width * height)
        else:
            # If size matches, apply fill if provided?
            # "idempotent" suggests we shouldn't overwrite existing data if it looks valid.
            # But if fill is specified, maybe we should?
            # Let's say fill is only for NEW initialization or if we force it.
            # The spec says "Optional fill spec".
            if lid in fill_map:
                fill_val = fill_map[lid]
                # Check if all 0?
                if all(t == 0 for t in current_tiles):
                    layer_obj["tiles"] = [fill_val] * (width * height)

        if lid == collision_layer_id:
            layer_obj["collision"] = True
        elif layer_obj.get("collision") and lid != collision_layer_id:
            # If this layer was collision but now we specified a different one?
            # The args say "Optional collision layer id". If provided, we set it.
            # If not provided, we leave as is?
            pass

    if _scene_validate_scene_payload(scene_path, data) != 0:
        return 1

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_resize(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    new_w = int(args.width)
    new_h = int(args.height)
    anchor_raw = str(getattr(args, "anchor", "tl") or "tl").strip().lower()
    anchor: Literal["tl", "center"] = "center" if anchor_raw == "center" else "tl"
    fill_tile = int(getattr(args, "fill_tile", 0))
    only_layers = set(getattr(args, "only_layer", []) or [])

    if new_w <= 0 or new_h <= 0:
        print("[Mesh][CLI] Error: dimensions must be positive")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-006", f"resize: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap must be an object: {scene_path}")
        return 1

    old_w = tilemap.get("width", 0)
    old_h = tilemap.get("height", 0)
    if not isinstance(old_w, int) or not isinstance(old_h, int):
        print(f"[Mesh][CLI] Error: invalid tilemap dimensions: {scene_path}")
        return 1

    tilemap["width"] = new_w
    tilemap["height"] = new_h

    layers = tilemap.get("tile_layers")
    if not isinstance(layers, list):
        layers = []
        tilemap["tile_layers"] = layers

    # Anchor logic
    # tl: (0,0) -> (0,0)
    # tr: (old_w, 0) -> (new_w, 0) => offset_x = new_w - old_w
    # bl: (0, old_h) -> (0, new_h) => offset_y = new_h - old_h
    # br: (old_w, old_h) -> (new_w, new_h) => offset_x = ..., offset_y = ...
    
    offset_x = 0
    offset_y = 0
    if "r" in anchor:
        offset_x = new_w - old_w
    if "b" in anchor:
        offset_y = new_h - old_h

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        lid = layer.get("id")
        if only_layers and lid not in only_layers:
            continue
        
        tiles = layer.get("tiles")
        if not isinstance(tiles, list):
            tiles = []
        
        # Reconstruct 2D
        # If old_w/h are 0, treat as empty
        src_grid = {}
        if old_w > 0 and old_h > 0:
            for i, t in enumerate(tiles):
                if i >= old_w * old_h: break
                y = i // old_w
                x = i % old_w
                src_grid[(x, y)] = t
        
        new_tiles = [fill_tile] * (new_w * new_h)
        
        # Map src to dst
        # dst_x = src_x + offset_x
        # dst_y = src_y + offset_y
        # So src_x = dst_x - offset_x
        
        for dy in range(new_h):
            for dx in range(new_w):
                sx = dx - offset_x
                sy = dy - offset_y
                if 0 <= sx < old_w and 0 <= sy < old_h:
                    val = src_grid.get((sx, sy), fill_tile)
                    new_tiles[dy * new_w + dx] = val
        
        layer["tiles"] = new_tiles

    if _scene_validate_scene_payload(scene_path, data) != 0:
        return 1

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_flood_fill(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    layer_id = str(getattr(args, "layer_id", "") or "").strip()
    start_x = int(args.x)
    start_y = int(args.y)
    new_tile = int(args.tile)
    target_tile = getattr(args, "target", None)
    max_tiles_value = getattr(args, "max_tiles", None)
    max_tiles = int(max_tiles_value) if max_tiles_value is not None else 5000
    diag = bool(getattr(args, "diag", False))
    clip = bool(getattr(args, "clip", False))

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-007", f"flood_fill: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap missing")
        return 1
    width = tilemap.get("width")
    height = tilemap.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or int(width) <= 0 or int(height) <= 0:
        print(f"[Mesh][CLI] Error: dims_missing scene={normalize_scene_path(scene_path)}")
        print("[Mesh][CLI] Hint: run `scene tilemap init` to set tilemap width/height.")
        return 1
    layers = tilemap.get("tile_layers", [])
    
    layer = next((L for L in layers if isinstance(L, dict) and L.get("id") == layer_id), None)
    if not layer:
        print(f"[Mesh][CLI] Error: layer not found: {layer_id}")
        return 1
    
    tiles = layer.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != int(width) * int(height):
        print(f"[Mesh][CLI] Error: layer tiles invalid size")
        return 1

    if not (0 <= start_x < int(width) and 0 <= start_y < int(height)):
        print(f"[Mesh][CLI] Error: out_of_bounds ({start_x},{start_y}) in {int(width)}x{int(height)}")
        return 1

    start_idx = int(start_y) * int(width) + int(start_x)
    start_value = tiles[start_idx]

    if target_tile is not None:
        target = int(target_tile)
    else:
        target = int(start_value)
    
    if target == new_tile:
        return 0

    try:
        indices = flood_fill_indices(
            tiles, int(width), int(height), int(start_x), int(start_y), int(target), diag=diag, max_tiles=max_tiles
        )
    except FloodFillMaxTilesExceeded as exc:
        if not clip:
            print(f"[Mesh][CLI] Error: max_tiles_exceeded max_tiles={exc.max_tiles} attempted={exc.attempted}")
            return 1
        indices = list(exc.partial_indices)
    except IndexError:
        print(f"[Mesh][CLI] Error: out_of_bounds ({start_x},{start_y}) in {int(width)}x{int(height)}")
        return 1
    except ValueError as exc:
        print(f"[Mesh][CLI] Error: {exc}")
        return 1

    if not indices:
        return 0

    layer["tiles"] = apply_flood_fill(tiles, indices, int(new_tile))

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_fill_rect(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    layer_id = str(getattr(args, "layer_id", "") or "").strip()
    x0 = int(args.x0)
    y0 = int(args.y0)
    x1 = int(args.x1)
    y1 = int(args.y1)
    tile = int(args.tile)

    if x0 > x1 or y0 > y1:
        print("[Mesh][CLI] Error: invalid rect; require x0<=x1 and y0<=y1")
        return 2

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-008", f"fill_rect: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap missing")
        return 1

    dims = _tilemap_resolve_dims_for_edit(scene_path_display=scene_path, scene_path=resolved, tilemap=tilemap)
    if dims is None:
        return 1
    width, height = dims

    _scene_tilemap_maybe_migrate_layers(tilemap)
    layers = tilemap.get("tile_layers", [])
    
    layer = next((L for L in layers if isinstance(L, dict) and L.get("id") == layer_id), None)
    if not layer:
        print(f"[Mesh][CLI] Error: layer not found: {layer_id}")
        return 1
    
    tiles = layer.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != width * height:
        print(f"[Mesh][CLI] Error: layer tiles invalid size")
        return 1

    if x0 < 0 or y0 < 0 or x1 < 0 or y1 < 0:
        print("[Mesh][CLI] Error: rect out of bounds")
        return 1
    if x1 >= width or y1 >= height:
        print("[Mesh][CLI] Error: rect out of bounds")
        return 1

    changed = False
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            idx = y * width + x
            if tiles[idx] != tile:
                tiles[idx] = tile
                changed = True

    if not changed:
        return 0

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_clear_rect(args: argparse.Namespace) -> int:
    # Just alias fill with 0
    args.tile = 0
    return _handle_scene_tilemap_fill_rect(args)


def _handle_scene_tilemap_paint(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    layer_id = str(getattr(args, "layer_id", "") or "").strip()
    x = int(args.x)
    y = int(args.y)
    tile = int(args.tile)

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-009", f"paint: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap missing")
        return 1

    dims = _tilemap_resolve_dims_for_edit(scene_path_display=scene_path, scene_path=resolved, tilemap=tilemap)
    if dims is None:
        return 1
    width, height = dims

    _scene_tilemap_maybe_migrate_layers(tilemap)
    layers = tilemap.get("tile_layers", [])
    
    layer = next((L for L in layers if isinstance(L, dict) and L.get("id") == layer_id), None)
    if not layer:
        print(f"[Mesh][CLI] Error: layer not found: {layer_id}")
        return 1
    
    tiles = layer.get("tiles")
    if tiles is None:
        tiles = [0] * (width * height)
        layer["tiles"] = tiles
    if not isinstance(tiles, list) or len(tiles) != width * height:
        print(f"[Mesh][CLI] Error: layer tiles invalid size")
        return 1

    if not (0 <= x < width and 0 <= y < height):
        print(f"[Mesh][CLI] Error: coordinates out of bounds")
        return 1

    idx = y * width + x
    if tiles[idx] == tile:
        return 0

    tiles[idx] = tile
    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _handle_scene_tilemap_brush(args: argparse.Namespace) -> int:
    scene_path = str(getattr(args, "scene_path", "") or "").strip()
    layer_id = str(getattr(args, "layer_id", "") or "").strip()
    brush_path = str(getattr(args, "brush", "") or "").strip()
    x = int(args.x)
    y = int(args.y)
    anchor_raw = str(getattr(args, "anchor", "tl") or "tl").strip().lower()
    anchor: Literal["tl", "center"] = "center" if anchor_raw == "center" else "tl"
    clip = bool(getattr(args, "clip", False))

    resolved = resolve_path(scene_path)
    if not resolved.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path}")
        return 1

    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: cli tilemap fallback isolation
        _log_swallow("TILE-010", f"brush: parse scene JSON failed: {scene_path}", once=False)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path}: {exc}")
        return 1

    tilemap = data.get("tilemap")
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: tilemap missing")
        return 1
    width = tilemap.get("width", 0)
    height = tilemap.get("height", 0)
    layers = tilemap.get("tile_layers", [])
    
    layer = next((L for L in layers if isinstance(L, dict) and L.get("id") == layer_id), None)
    if not layer:
        print(f"[Mesh][CLI] Error: layer not found: {layer_id}")
        return 1
    
    tiles = layer.get("tiles")
    if not isinstance(tiles, list) or len(tiles) != width * height:
        print(f"[Mesh][CLI] Error: layer tiles invalid size")
        return 1

    # Load brush
    brush_loader = BrushLoader()
    try:
        brush = brush_loader.load_brush(brush_path)
    except Exception as e:
        _log_swallow("TILE-011", f"brush load failed: {brush_path}", once=False)
        print(f"[Mesh][CLI] Error loading brush: {e}")
        return 1

    # Apply brush
    # We need to adapt apply_brush to work with our data structure or just do it manually.
    # engine.brushes.apply_brush takes (tiles, width, height, brush, x, y, anchor, clip)
    
    try:
        new_tiles = apply_brush(tiles, width=width, height=height, x=x, y=y, brush=brush, anchor=anchor, clip=clip)
    except (ValueError, IndexError) as e:
        print(f"[Mesh][CLI] Error applying brush: {e}")
        return 1
        
    layer["tiles"] = new_tiles

    compacted = compact_scene_payload(data)
    write_json_atomic(resolved, compacted, indent=2, sort_keys=False, trailing_newline=True)
    return 0


def _scene_tilemap_maybe_migrate_layers(tilemap: dict) -> None:
    if "tile_layers" in tilemap:
        return
    legacy = tilemap.get("layers")
    if legacy is None:
        tilemap["tile_layers"] = []
        return

    def iter_legacy_layers(raw: Any) -> list[dict]:
        out: list[dict] = []
        if isinstance(raw, dict):
            for name, cfg in raw.items():
                if not isinstance(name, str) or not name.strip() or not isinstance(cfg, dict):
                    continue
                out.append({"name": name.strip(), **cfg})
        elif isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    out.append(entry)
        return out

    def parse_legacy_z(value: Any) -> int:
        if isinstance(value, int):
            return int(value)
        text = str(value or "").strip().lower()
        if text == "foreground":
            return 100
        return -100

    migrated: list[dict[str, Any]] = []
    for entry in iter_legacy_layers(legacy):
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        migrated.append(
            {
                "id": name.strip(),
                "z": parse_legacy_z(entry.get("z", "background")),
                "parallax": float(entry.get("parallax", 1.0)),
                "draw": bool(entry.get("draw", True)),
                "collision": bool(entry.get("collision", False)),
            }
        )
    tilemap["tile_layers"] = migrated


def _tilemap_resolve_dims_for_edit(
    *,
    scene_path_display: str,
    scene_path: Path,
    tilemap: dict,
) -> tuple[int, int] | None:
    map_path_value = tilemap.get("resolved_path") or tilemap.get("path")
    if isinstance(map_path_value, str) and map_path_value.strip():
        raw_map_path = map_path_value.strip()
        candidate_path = Path(raw_map_path)
        map_candidates: list[Path] = []
        if candidate_path.is_absolute():
            map_candidates.append(candidate_path)
        else:
            map_candidates.append((scene_path.parent / candidate_path).resolve())
            map_candidates.append((Path.cwd() / candidate_path).resolve())

        chosen_map_path = map_candidates[-1] if map_candidates else candidate_path
        for candidate in map_candidates:
            if candidate.exists():
                chosen_map_path = candidate
                break

        try:
            tiled = json.loads(chosen_map_path.read_text(encoding="utf-8"))
            w = int(tiled.get("width", 0))
            h = int(tiled.get("height", 0))
            if w > 0 and h > 0:
                return w, h
        except Exception:
            _log_swallow("TILE-002", "mesh_cli/scene/tilemap.py pass-only blanket swallow")
            pass

    w_value = tilemap.get("width")
    h_value = tilemap.get("height")
    if w_value is None or h_value is None:
        print(f"[Mesh][CLI] Error: cannot determine tilemap dimensions for {scene_path_display}")
        print("[Mesh][CLI] Provide a valid tilemap.path (with width/height) or scene.tilemap.width/height.")
        return None
    try:
        w = int(w_value)
        h = int(h_value)
    except Exception:
        _log_swallow("TILE-012", f"cannot determine tilemap dims for {scene_path_display}", once=False)
        print(f"[Mesh][CLI] Error: cannot determine tilemap dimensions for {scene_path_display}")
        print("[Mesh][CLI] Provide a valid tilemap.path (with width/height) or scene.tilemap.width/height.")
        return None
    if w <= 0 or h <= 0:
        print(f"[Mesh][CLI] Error: invalid tilemap.width/height for {scene_path_display}: {w}x{h}")
        return None
    return w, h


def _tilemap_try_resolve_tile_size_for_stamp(
    *,
    scene_path: Path,
    tilemap: dict,
) -> tuple[int, int] | None:
    tw_scene = tilemap.get("tilewidth")
    th_scene = tilemap.get("tileheight")
    if isinstance(tw_scene, int) and isinstance(th_scene, int) and int(tw_scene) > 0 and int(th_scene) > 0:
        return int(tw_scene), int(th_scene)

    map_path_value = tilemap.get("resolved_path") or tilemap.get("path")
    if not isinstance(map_path_value, str) or not map_path_value.strip():
        return None

    raw_map_path = map_path_value.strip()
    candidate_path = Path(raw_map_path)
    map_candidates: list[Path] = []
    if candidate_path.is_absolute():
        map_candidates.append(candidate_path)
    else:
        map_candidates.append((scene_path.parent / candidate_path).resolve())
        map_candidates.append((Path.cwd() / candidate_path).resolve())

    chosen_map_path = map_candidates[-1] if map_candidates else candidate_path
    for candidate in map_candidates:
        if candidate.exists():
            chosen_map_path = candidate
            break

    try:
        tiled = json.loads(chosen_map_path.read_text(encoding="utf-8"))
    except Exception:
        _log_swallow("TILE-013", f"tile size: failed to parse map: {chosen_map_path}")
        return None
    try:
        tw = int(tiled.get("tilewidth", 0))
        th = int(tiled.get("tileheight", 0))
    except Exception:
        _log_swallow("TILE-014", f"tile size: int conversion failed for map: {chosen_map_path}")
        return None
    if tw > 0 and th > 0:
        return tw, th
    return None
