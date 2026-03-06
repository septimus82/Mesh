import argparse
import json
from pathlib import Path
from typing import Any, cast

from engine.paths import resolve_path
from engine.persistence_io import write_json_atomic
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload
from engine.tilemap_edit import TilemapDims, ensure_tiles_array, fill_rect, get_layer_by_id
from engine.tooling_runtime.stamp_report import StampReportError, compute_scene_stamp_report
from engine.path_norm import normalize_scene_path

from mesh_cli.scene.common import _sanitize_entity_id_token
from mesh_cli.scene.tilemap import (
    _tilemap_resolve_dims_for_edit,
    _scene_tilemap_maybe_migrate_layers,
    _tilemap_try_resolve_tile_size_for_stamp,
    _tilemap_validate_scene_payload,
)

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def _default_stamp_entity_id(
    scene_path: str,
    *,
    id_prefix: str,
    id_suffix: str,
    origin_x: int,
    origin_y: int,
) -> str:
    stem = Path(str(scene_path)).stem
    stem = _sanitize_entity_id_token(stem)
    prefix = _sanitize_entity_id_token(id_prefix)
    suffix = _sanitize_entity_id_token(id_suffix)
    return f"{stem}_{prefix}_{suffix}_{origin_x}_{origin_y}_0_0"


class _StampReportError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = int(exit_code)


def _compute_scene_stamp_report_legacy_do_not_use(
    *,
    scene_path_display: str,
    stamp_path_raw: str,
    origin_x: int,
    origin_y: int,
    id_prefix: str,
) -> dict[str, Any]:
    """Compute a dry-run report of what `scene stamp` would change (no writes)."""
    resolved_scene = resolve_path(scene_path_display)
    if not resolved_scene.exists():
        raise _StampReportError(f"scene not found: {scene_path_display}")

    resolved_stamp = resolve_path(stamp_path_raw)
    if not resolved_stamp.exists():
        raise _StampReportError(f"stamp not found: {stamp_path_raw}")

    try:
        raw_scene = json.loads(resolved_scene.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
        raise _StampReportError(f"failed to parse scene JSON: {scene_path_display}: {exc}") from exc
    if not isinstance(raw_scene, dict):
        raise _StampReportError(f"scene JSON root must be an object: {scene_path_display}")

    try:
        stamp = json.loads(resolved_stamp.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
        raise _StampReportError(f"failed to parse stamp JSON: {stamp_path_raw}: {exc}") from exc
    if not isinstance(stamp, dict):
        raise _StampReportError(f"stamp JSON root must be an object: {stamp_path_raw}")

    stamp_id = stamp.get("id")
    if not isinstance(stamp_id, str) or not stamp_id.strip():
        raise _StampReportError("stamp.id must be a non-empty string")
    stamp_id = stamp_id.strip()

    try:
        stamp_w = int(stamp.get("width", 0))
        stamp_h = int(stamp.get("height", 0))
    except Exception:  # noqa: BLE001  # REASON: scene stamp command isolation
        _log_swallow("STMP-014", "stamp width/height parse", once=True)
        stamp_w = 0
        stamp_h = 0
    if stamp_w <= 0 or stamp_h <= 0:
        raise _StampReportError("stamp.width/stamp.height must be positive integers")

    resolved_id_prefix = str(id_prefix or "").strip() or stamp_id

    loader = SceneLoader()
    scene = loader.apply_scene_defaults(raw_scene)

    entities_value = scene.get("entities")
    if entities_value is None:
        entities: list[dict[str, Any]] = []
        scene["entities"] = entities
    elif isinstance(entities_value, list):
        if any(not isinstance(row, dict) for row in entities_value):
            raise _StampReportError(f"scene.entities entries must be objects: {scene_path_display}")
        entities = cast(list[dict[str, Any]], entities_value)
    else:
        raise _StampReportError(f"scene.entities must be a list: {scene_path_display}")

    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict):
        raise _StampReportError(f"scene has no tilemap section: {scene_path_display}")

    dims_raw = _tilemap_resolve_dims_for_edit(
        scene_path_display=scene_path_display,
        scene_path=resolved_scene,
        tilemap=tilemap,
    )
    if dims_raw is None:
        raise _StampReportError("tilemap dims missing", exit_code=1)
    dims = TilemapDims(width=dims_raw[0], height=dims_raw[1])

    _scene_tilemap_maybe_migrate_layers(tilemap)
    tile_layers = tilemap.get("tile_layers")
    if not isinstance(tile_layers, list):
        raise _StampReportError(f"tilemap.tile_layers must be a list: {scene_path_display}")

    prefabs_path = resolve_path("assets/prefabs.json")
    try:
        prefabs_payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
        raise _StampReportError(f"failed to read prefabs: {prefabs_path}: {exc}") from exc
    if not isinstance(prefabs_payload, list):
        raise _StampReportError(f"prefabs payload must be a list: {prefabs_path}")
    known_prefabs: set[str] = {
        str(entry.get("id"))
        for entry in prefabs_payload
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    stamp_entities_value = stamp.get("entities", [])
    if stamp_entities_value is None:
        stamp_entities_value = []
    if not isinstance(stamp_entities_value, list):
        raise _StampReportError("stamp.entities must be an array when provided")

    for idx, entry in enumerate(stamp_entities_value):
        if not isinstance(entry, dict):
            raise _StampReportError(f"stamp.entities[{idx}] must be an object")
        prefab_id = entry.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            raise _StampReportError(f"stamp.entities[{idx}].prefab_id must be a non-empty string")
        if prefab_id.strip() not in known_prefabs:
            raise _StampReportError(f"stamp.entities[{idx}] prefab_id not found: {prefab_id}")

    tile_size = _tilemap_try_resolve_tile_size_for_stamp(scene_path=resolved_scene, tilemap=tilemap)

    tile_changes_by_layer: dict[str, dict[int, tuple[int, int]]] = {}

    stamp_tiles_value = stamp.get("tiles", [])
    if stamp_tiles_value is None:
        stamp_tiles_value = []
    if not isinstance(stamp_tiles_value, list):
        raise _StampReportError("stamp.tiles must be an array when provided")

    tiles_cache: dict[str, list[int]] = {}

    for idx, entry in enumerate(stamp_tiles_value):
        if not isinstance(entry, dict):
            raise _StampReportError(f"stamp.tiles[{idx}] must be an object")

        layer_id = entry.get("layer_id")
        if not isinstance(layer_id, str) or not layer_id.strip():
            raise _StampReportError(f"stamp.tiles[{idx}].layer_id must be a non-empty string")
        layer_id = layer_id.strip()

        x_value = entry.get("x")
        y_value = entry.get("y")
        w_value = entry.get("w")
        h_value = entry.get("h")
        tile_value = entry.get("tile")
        if x_value is None or y_value is None or w_value is None or h_value is None or tile_value is None:
            raise _StampReportError(f"stamp.tiles[{idx}] x/y/w/h/tile must be integers")
        try:
            rel_x = int(x_value)
            rel_y = int(y_value)
            w = int(w_value)
            h = int(h_value)
            tile = int(tile_value)
        except Exception as exc:
            raise _StampReportError(f"stamp.tiles[{idx}] x/y/w/h/tile must be integers") from exc

        if w <= 0 or h <= 0:
            raise _StampReportError(f"stamp.tiles[{idx}] w/h must be > 0")
        if rel_x < 0 or rel_y < 0 or rel_x + w > stamp_w or rel_y + h > stamp_h:
            raise _StampReportError(f"stamp.tiles[{idx}] rect out of stamp bounds")

        x0 = origin_x + rel_x
        y0 = origin_y + rel_y
        x1 = x0 + w - 1
        y1 = y0 + h - 1

        try:
            layer = get_layer_by_id(tile_layers, layer_id)
        except KeyError as exc:
            raise _StampReportError(f"tile layer not found: {layer_id}") from exc

        if layer_id not in tiles_cache:
            tiles_cache[layer_id] = ensure_tiles_array(layer, dims=dims)

        tiles = tiles_cache[layer_id]
        if x0 < 0 or y0 < 0 or x1 >= dims.width or y1 >= dims.height:
            raise _StampReportError(f"stamp tile rect out of bounds for layer '{layer_id}': rect out of bounds")

        changes = tile_changes_by_layer.setdefault(layer_id, {})
        for yy in range(int(y0), int(y1) + 1):
            row_start = int(yy) * int(dims.width)
            for xx in range(int(x0), int(x1) + 1):
                cell_idx = row_start + int(xx)
                if cell_idx not in changes:
                    changes[cell_idx] = (int(tiles[cell_idx]), int(tiles[cell_idx]))
                before, _after = changes[cell_idx]
                changes[cell_idx] = (int(before), int(tile))
                tiles[cell_idx] = int(tile)

    entity_changes: list[dict[str, Any]] = []
    for idx, entry in enumerate(stamp_entities_value):
        if not isinstance(entry, dict):
            continue
        prefab_id = str(entry.get("prefab_id") or "").strip()
        id_suffix = entry.get("id_suffix")
        if not isinstance(id_suffix, str) or not id_suffix.strip():
            raise _StampReportError(f"stamp.entities[{idx}].id_suffix must be a non-empty string")
        id_suffix = id_suffix.strip()
        x_value = entry.get("x")
        y_value = entry.get("y")
        if x_value is None or y_value is None:
            raise _StampReportError(f"stamp.entities[{idx}].x/y must be integers")
        try:
            rel_x = int(x_value)
            rel_y = int(y_value)
        except Exception as exc:
            raise _StampReportError(f"stamp.entities[{idx}].x/y must be integers") from exc
        if rel_x < 0 or rel_y < 0 or rel_x >= stamp_w or rel_y >= stamp_h:
            raise _StampReportError(f"stamp.entities[{idx}] position out of stamp bounds")

        entity_id = _default_stamp_entity_id(
            scene_path_display,
            id_prefix=resolved_id_prefix,
            id_suffix=id_suffix,
            origin_x=origin_x,
            origin_y=origin_y,
        )

        if tile_size is not None:
            tw, th = tile_size
            desired_x = (origin_x + rel_x + 0.5) * float(tw)
            desired_y = (origin_y + rel_y + 0.5) * float(th)
        else:
            desired_x = float(origin_x + rel_x)
            desired_y = float(origin_y + rel_y)

        existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
        if existing is None:
            entity_changes.append(
                {
                    "id": entity_id,
                    "action": "add",
                    "prefab_id": prefab_id,
                    "x": float(desired_x),
                    "y": float(desired_y),
                }
            )
            continue

        if str(existing.get("prefab_id") or "") != prefab_id:
            raise _StampReportError(
                f"prefab_mismatch: {entity_id} (expected {prefab_id}, got {existing.get('prefab_id')})"
            )

        if float(existing.get("x", desired_x)) != float(desired_x) or float(existing.get("y", desired_y)) != float(
            desired_y
        ):
            entity_changes.append(
                {
                    "id": entity_id,
                    "action": "update",
                    "prefab_id": prefab_id,
                    "x": float(desired_x),
                    "y": float(desired_y),
                }
            )

    tile_changes: list[dict[str, Any]] = []
    for layer_id in sorted(tile_changes_by_layer):
        for cell_idx in sorted(tile_changes_by_layer[layer_id].keys()):
            before, after = tile_changes_by_layer[layer_id][cell_idx]
            if int(before) == int(after):
                continue
            x = int(cell_idx) % int(dims.width)
            y = int(cell_idx) // int(dims.width)
            tile_changes.append(
                {
                    "layer_id": layer_id,
                    "x": int(x),
                    "y": int(y),
                    "before": int(before),
                    "after": int(after),
                }
            )
    tile_changes.sort(key=lambda row: (row["layer_id"], int(row["y"]), int(row["x"])))

    entity_changes.sort(key=lambda row: str(row.get("id") or ""))

    return {
        "ok": True,
        "scene_path": normalize_scene_path(scene_path_display),
        "stamp_path": normalize_scene_path(stamp_path_raw),
        "origin": {"x": int(origin_x), "y": int(origin_y)},
        "tile_changes": tile_changes,
        "entity_changes": entity_changes,
    }


def _handle_scene_stamp_report_legacy(args: argparse.Namespace) -> int:
    """Legacy stamp-report implementation (kept for compatibility and monkeypatch seams)."""
    scene_path_display = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path_display:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    stamp_path_raw = str(getattr(args, "stamp", "") or "").strip()
    if not stamp_path_raw:
        print("[Mesh][CLI] Error: missing --stamp")
        return 2

    origin_x = int(getattr(args, "x"))
    origin_y = int(getattr(args, "y"))

    format_value = str(getattr(args, "format", "json") or "json").strip().lower()
    if format_value not in {"json", "text"}:
        print("[Mesh][CLI] Error: invalid --format")
        return 2

    id_prefix = str(getattr(args, "id_prefix", "") or "").strip()

    try:
        payload = _compute_scene_stamp_report_legacy_do_not_use(
            scene_path_display=scene_path_display,
            stamp_path_raw=stamp_path_raw,
            origin_x=origin_x,
            origin_y=origin_y,
            id_prefix=id_prefix,
        )
    except _StampReportError as exc:
        print(f"[Mesh][CLI] Error: {exc.message}")
        return int(exc.exit_code)

    if format_value == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(
        f"stamp-report scene={payload['scene_path']} stamp={payload['stamp_path']} origin=({origin_x},{origin_y}) "
        f"tile_changes={len(payload['tile_changes'])} entity_changes={len(payload['entity_changes'])}",
    )
    for row in payload["tile_changes"]:
        print(
            f"tile {row['layer_id']} ({row['x']},{row['y']}) {row['before']}->{row['after']}",
        )
    for row in payload["entity_changes"]:
        print(
            f"entity {row['action']} {row['id']} prefab={row['prefab_id']} x={row['x']:.3f} y={row['y']:.3f}",
        )
    return 0


def _handle_scene_stamp(args: argparse.Namespace) -> int:
    """Apply a stamp JSON: tile edits + optional prefab entity placements (idempotent)."""
    scene_path_display = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path_display:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    stamp_path_raw = str(getattr(args, "stamp", "") or "").strip()
    if not stamp_path_raw:
        print("[Mesh][CLI] Error: missing --stamp")
        return 2

    origin_x = int(getattr(args, "x"))
    origin_y = int(getattr(args, "y"))

    resolved_scene = resolve_path(scene_path_display)
    if not resolved_scene.exists():
        print(f"[Mesh][CLI] Error: scene not found: {scene_path_display}")
        return 1

    resolved_stamp = resolve_path(stamp_path_raw)
    if not resolved_stamp.exists():
        print(f"[Mesh][CLI] Error: stamp not found: {stamp_path_raw}")
        return 1

    try:
        raw_scene = json.loads(resolved_scene.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
        _log_swallow("STMP-015", "apply scene JSON parse", once=True)
        print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path_display}: {exc}")
        return 1
    if not isinstance(raw_scene, dict):
        print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path_display}")
        return 1

    try:
        stamp = json.loads(resolved_stamp.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
        _log_swallow("STMP-016", "apply stamp JSON parse", once=True)
        print(f"[Mesh][CLI] Error: failed to parse stamp JSON: {stamp_path_raw}: {exc}")
        return 1
    if not isinstance(stamp, dict):
        print(f"[Mesh][CLI] Error: stamp JSON root must be an object: {stamp_path_raw}")
        return 1

    stamp_id = stamp.get("id")
    if not isinstance(stamp_id, str) or not stamp_id.strip():
        print("[Mesh][CLI] Error: stamp.id must be a non-empty string")
        return 1
    stamp_id = stamp_id.strip()

    try:
        stamp_w = int(stamp.get("width", 0))
        stamp_h = int(stamp.get("height", 0))
    except Exception:  # noqa: BLE001  # REASON: scene stamp command isolation
        _log_swallow("STMP-017", "apply stamp width/height parse", once=True)
        stamp_w = 0
        stamp_h = 0
    if stamp_w <= 0 or stamp_h <= 0:
        print("[Mesh][CLI] Error: stamp.width/stamp.height must be positive integers")
        return 1

    id_prefix = str(getattr(args, "id_prefix", "") or "").strip() or stamp_id

    loader = SceneLoader()
    scene = loader.apply_scene_defaults(raw_scene)

    entities_value = scene.get("entities")
    if entities_value is None:
        entities: list[dict[str, Any]] = []
        scene["entities"] = entities
    elif isinstance(entities_value, list):
        if any(not isinstance(row, dict) for row in entities_value):
            print(f"[Mesh][CLI] Error: scene.entities entries must be objects: {scene_path_display}")
            return 1
        entities = cast(list[dict[str, Any]], entities_value)
    else:
        print(f"[Mesh][CLI] Error: scene.entities must be a list: {scene_path_display}")
        return 1

    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict):
        print(f"[Mesh][CLI] Error: scene has no tilemap section: {scene_path_display}")
        return 1

    dims_raw = _tilemap_resolve_dims_for_edit(
        scene_path_display=scene_path_display,
        scene_path=resolved_scene,
        tilemap=tilemap,
    )
    if dims_raw is None:
        return 1
    dims = TilemapDims(width=dims_raw[0], height=dims_raw[1])

    _scene_tilemap_maybe_migrate_layers(tilemap)
    tile_layers = tilemap.get("tile_layers")
    if not isinstance(tile_layers, list):
        print(f"[Mesh][CLI] Error: tilemap.tile_layers must be a list: {scene_path_display}")
        return 1

    # Prefab existence: load once and check all entity prefabs before mutating.
    prefabs_path = resolve_path("assets/prefabs.json")
    try:
        prefabs_payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
        _log_swallow("STMP-018", "prefabs JSON parse", once=True)
        print(f"[Mesh][CLI] Error: failed to read prefabs: {prefabs_path}: {exc}")
        return 1
    if not isinstance(prefabs_payload, list):
        print(f"[Mesh][CLI] Error: prefabs payload must be a list: {prefabs_path}")
        return 1
    known_prefabs: set[str] = {
        str(entry.get("id"))
        for entry in prefabs_payload
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    stamp_entities_value = stamp.get("entities", [])
    if stamp_entities_value is None:
        stamp_entities_value = []
    if not isinstance(stamp_entities_value, list):
        print("[Mesh][CLI] Error: stamp.entities must be an array when provided")
        return 1

    for idx, entry in enumerate(stamp_entities_value):
        if not isinstance(entry, dict):
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}] must be an object")
            return 1
        prefab_id = entry.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}].prefab_id must be a non-empty string")
            return 1
        if prefab_id.strip() not in known_prefabs:
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}] prefab_id not found: {prefab_id}")
            return 1

    tile_size = _tilemap_try_resolve_tile_size_for_stamp(scene_path=resolved_scene, tilemap=tilemap)

    changed = False

    stamp_tiles_value = stamp.get("tiles", [])
    if stamp_tiles_value is None:
        stamp_tiles_value = []
    if not isinstance(stamp_tiles_value, list):
        print("[Mesh][CLI] Error: stamp.tiles must be an array when provided")
        return 1

    tiles_cache: dict[str, list[int]] = {}
    for idx, entry in enumerate(stamp_tiles_value):
        if not isinstance(entry, dict):
            print(f"[Mesh][CLI] Error: stamp.tiles[{idx}] must be an object")
            return 1

        layer_id = entry.get("layer_id")
        if not isinstance(layer_id, str) or not layer_id.strip():
            print(f"[Mesh][CLI] Error: stamp.tiles[{idx}].layer_id must be a non-empty string")
            return 1
        layer_id = layer_id.strip()

        x_value = entry.get("x")
        y_value = entry.get("y")
        w_value = entry.get("w")
        h_value = entry.get("h")
        tile_value = entry.get("tile")
        if x_value is None or y_value is None or w_value is None or h_value is None or tile_value is None:
            print(f"[Mesh][CLI] Error: stamp.tiles[{idx}] x/y/w/h/tile must be integers")
            return 1
        try:
            rel_x = int(x_value)
            rel_y = int(y_value)
            w = int(w_value)
            h = int(h_value)
            tile = int(tile_value)
        except Exception:  # noqa: BLE001  # REASON: scene stamp command isolation
            _log_swallow("STMP-019", "apply tile coords parse", once=True)
            print(f"[Mesh][CLI] Error: stamp.tiles[{idx}] x/y/w/h/tile must be integers")
            return 1

        if w <= 0 or h <= 0:
            print(f"[Mesh][CLI] Error: stamp.tiles[{idx}] w/h must be > 0")
            return 1
        if rel_x < 0 or rel_y < 0 or rel_x + w > stamp_w or rel_y + h > stamp_h:
            print(f"[Mesh][CLI] Error: stamp.tiles[{idx}] rect out of stamp bounds")
            return 1

        x0 = origin_x + rel_x
        y0 = origin_y + rel_y
        x1 = x0 + w - 1
        y1 = y0 + h - 1

        try:
            layer = get_layer_by_id(tile_layers, layer_id)
        except KeyError:
            print(f"[Mesh][CLI] Error: tile layer not found: {layer_id}")
            return 1

        if layer_id not in tiles_cache:
            tiles_cache[layer_id] = ensure_tiles_array(layer, dims=dims)
        try:
            if fill_rect(tiles_cache[layer_id], dims=dims, x0=x0, y0=y0, x1=x1, y1=y1, tile=tile):
                changed = True
        except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
            _log_swallow("STMP-020", "fill_rect bounds", once=True)
            print(f"[Mesh][CLI] Error: stamp tile rect out of bounds for layer '{layer_id}': {exc}")
            return 1

    for idx, entry in enumerate(stamp_entities_value):
        if not isinstance(entry, dict):
            continue
        prefab_id = str(entry.get("prefab_id") or "").strip()
        id_suffix = entry.get("id_suffix")
        if not isinstance(id_suffix, str) or not id_suffix.strip():
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}].id_suffix must be a non-empty string")
            return 1
        id_suffix = id_suffix.strip()
        x_value = entry.get("x")
        y_value = entry.get("y")
        if x_value is None or y_value is None:
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}].x/y must be integers")
            return 1
        try:
            rel_x = int(x_value)
            rel_y = int(y_value)
        except Exception:  # noqa: BLE001  # REASON: scene stamp command isolation
            _log_swallow("STMP-021", "apply entity coords parse", once=True)
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}].x/y must be integers")
            return 1
        if rel_x < 0 or rel_y < 0 or rel_x >= stamp_w or rel_y >= stamp_h:
            print(f"[Mesh][CLI] Error: stamp.entities[{idx}] position out of stamp bounds")
            return 1

        entity_id = _default_stamp_entity_id(
            scene_path_display,
            id_prefix=id_prefix,
            id_suffix=id_suffix,
            origin_x=origin_x,
            origin_y=origin_y,
        )

        if tile_size is not None:
            tw, th = tile_size
            desired_x = (origin_x + rel_x + 0.5) * float(tw)
            desired_y = (origin_y + rel_y + 0.5) * float(th)
        else:
            desired_x = float(origin_x + rel_x)
            desired_y = float(origin_y + rel_y)

        existing = next((e for e in entities if isinstance(e, dict) and e.get("id") == entity_id), None)
        if existing is None:
            entities.append(
                {
                    "id": entity_id,
                    "prefab_id": prefab_id,
                    "layer": "entities",
                    "x": float(desired_x),
                    "y": float(desired_y),
                }
            )
            changed = True
            continue

        if str(existing.get("prefab_id") or "") != prefab_id:
            print(
                f"[Mesh][CLI] Error: stamp entity id already exists with different prefab: {entity_id} "
                f"(expected {prefab_id}, got {existing.get('prefab_id')})",
            )
            return 1

        if float(existing.get("x", desired_x)) != float(desired_x):
            existing["x"] = float(desired_x)
            changed = True
        if float(existing.get("y", desired_y)) != float(desired_y):
            existing["y"] = float(desired_y)
            changed = True

    if not changed:
        return 0

    _normalized_scene_path, errors = _tilemap_validate_scene_payload(scene_path_display, resolved_scene, scene)
    if errors:
        for scene_id, layer_key, field, message in errors:
            layer_label = layer_key or "-"
            print(f"[Mesh][Tilemap] ERROR: {scene_id} :: {layer_label} :: {field} :: {message}")
        return 1

    report = loader.validate_scene(scene, strict=False)
    if not report.ok:
        print(f"[Mesh][CLI] Error: scene validation failed after stamp: {scene_path_display}")
        for msg in report.errors:
            print(f"[Mesh][CLI] ERROR: {msg}")
        return 1

    compacted = compact_scene_payload(scene)
    write_json_atomic(resolved_scene, compacted, indent=2, sort_keys=True, trailing_newline=True)
    return 0


def _handle_scene_stamp_report(args: argparse.Namespace) -> int:
    """Compute a dry-run report of what `scene stamp` would change (no writes)."""
    scene_path_display = str(getattr(args, "scene_path", "") or "").strip()
    if not scene_path_display:
        print("[Mesh][CLI] Error: missing scene_path")
        return 2

    stamp_path_raw = str(getattr(args, "stamp", "") or "").strip()
    if not stamp_path_raw:
        print("[Mesh][CLI] Error: missing --stamp")
        return 2

    origin_x = int(getattr(args, "x"))
    origin_y = int(getattr(args, "y"))

    format_value = str(getattr(args, "format", "json") or "json").strip().lower()
    if format_value not in {"json", "text"}:
        print("[Mesh][CLI] Error: invalid --format")
        return 2

    id_prefix = str(getattr(args, "id_prefix", "") or "").strip()
    try:
        resolved_scene = resolve_path(scene_path_display)
        if not resolved_scene.exists():
            print(f"[Mesh][CLI] Error: scene not found: {scene_path_display}")
            return 1

        resolved_stamp = resolve_path(stamp_path_raw)
        if not resolved_stamp.exists():
            print(f"[Mesh][CLI] Error: stamp not found: {stamp_path_raw}")
            return 1

        try:
            raw_scene = json.loads(resolved_scene.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
            _log_swallow("STMP-022", "report scene JSON parse", once=True)
            print(f"[Mesh][CLI] Error: failed to parse scene JSON: {scene_path_display}: {exc}")
            return 1
        if not isinstance(raw_scene, dict):
            print(f"[Mesh][CLI] Error: scene JSON root must be an object: {scene_path_display}")
            return 1

        try:
            stamp = json.loads(resolved_stamp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  # REASON: scene stamp command isolation
            _log_swallow("STMP-023", "report stamp JSON parse", once=True)
            print(f"[Mesh][CLI] Error: failed to parse stamp JSON: {stamp_path_raw}: {exc}")
            return 1
        if not isinstance(stamp, dict):
            print(f"[Mesh][CLI] Error: stamp JSON root must be an object: {stamp_path_raw}")
            return 1

        raw_scene["_mesh_source_path"] = scene_path_display
        stamp["_mesh_source_path"] = stamp_path_raw

        payload = compute_scene_stamp_report(raw_scene, stamp, origin_x, origin_y, id_prefix)
    except StampReportError as exc:
        print(f"[Mesh][CLI] Error: {exc.message}")
        return exc.exit_code

    if format_value == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(
        f"stamp-report scene={payload['scene_path']} stamp={payload['stamp_path']} origin=({origin_x},{origin_y}) "
        f"tile_changes={len(payload['tile_changes'])} entity_changes={len(payload['entity_changes'])}",
    )
    for row in payload["tile_changes"]:
        print(
            f"tile {row['layer_id']} ({row['x']},{row['y']}) {row['before']}->{row['after']}",
        )
    for row in payload["entity_changes"]:
        print(
            f"entity {row['action']} {row['id']} prefab={row['prefab_id']} x={row['x']:.3f} y={row['y']:.3f}",
        )
    return 0
