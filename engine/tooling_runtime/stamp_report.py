from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path
from engine.scene_loader import SceneLoader
from engine.tilemap_edit import TilemapDims, ensure_tiles_array, get_layer_by_id


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


class StampReportError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = int(exit_code)


def _sanitize_entity_id_token(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "x"
    out: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_"}:
            out.append(ch)
        elif ch in {".", "-", ":", "/", "\\", " "}:
            out.append("_")
        else:
            out.append("_")
    collapsed = "".join(out)
    while "__" in collapsed:
        collapsed = collapsed.replace("__", "_")
    return collapsed.strip("_") or "x"


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
            _log_swallow("STAM-001", "engine/tooling_runtime/stamp_report.py pass-only blanket swallow")
            pass

    w_value = tilemap.get("width")
    h_value = tilemap.get("height")
    try:
        w = int(cast(Any, w_value))
        h = int(cast(Any, h_value))
    except Exception:
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
        return None
    try:
        tw = int(tiled.get("tilewidth", 0))
        th = int(tiled.get("tileheight", 0))
    except Exception:
        return None
    if tw > 0 and th > 0:
        return tw, th
    return None


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


def compute_scene_stamp_report(
    scene_payload: dict[str, Any],
    stamp_payload: dict[str, Any],
    origin_x: int,
    origin_y: int,
    id_prefix: str,
    ignore_prefab_mismatch: bool = False,
) -> dict[str, Any]:
    """Compute a dry-run report of what `scene stamp` would change (no writes).

    Expects `scene_payload` and `stamp_payload` to be raw JSON dictionaries loaded from disk.
    For stable output paths, callers may set `_mesh_source_path` on each payload.
    """
    scene_path_display = str(scene_payload.get("_mesh_source_path") or "").strip()
    stamp_path_raw = str(stamp_payload.get("_mesh_source_path") or "").strip()

    stamp_id = stamp_payload.get("id")
    if not isinstance(stamp_id, str) or not stamp_id.strip():
        raise StampReportError("stamp.id must be a non-empty string")
    stamp_id = stamp_id.strip()

    try:
        stamp_w = int(stamp_payload.get("width", 0))
        stamp_h = int(stamp_payload.get("height", 0))
    except Exception:
        stamp_w = 0
        stamp_h = 0
    if stamp_w <= 0 or stamp_h <= 0:
        raise StampReportError("stamp.width/stamp.height must be positive integers")

    resolved_id_prefix = str(id_prefix or "").strip() or stamp_id

    loader = SceneLoader()
    scene = loader.apply_scene_defaults(dict(scene_payload))

    entities_value = scene.get("entities")
    if entities_value is None:
        entities: list[dict[str, Any]] = []
        scene["entities"] = entities
    elif isinstance(entities_value, list):
        entities = entities_value
    else:
        raise StampReportError(f"scene.entities must be a list: {scene_path_display}")

    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict):
        raise StampReportError(f"scene has no tilemap section: {scene_path_display}")

    resolved_scene_path = resolve_path(scene_path_display) if scene_path_display else Path.cwd()

    dims_raw = _tilemap_resolve_dims_for_edit(
        scene_path_display=scene_path_display,
        scene_path=resolved_scene_path,
        tilemap=tilemap,
    )
    if dims_raw is None:
        raise StampReportError("tilemap dims missing", exit_code=1)
    dims = TilemapDims(width=dims_raw[0], height=dims_raw[1])

    _scene_tilemap_maybe_migrate_layers(tilemap)
    tile_layers = tilemap.get("tile_layers")
    if not isinstance(tile_layers, list):
        raise StampReportError(f"tilemap.tile_layers must be a list: {scene_path_display}")

    prefabs_path = resolve_path("assets/prefabs.json")
    try:
        prefabs_payload = json.loads(prefabs_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise StampReportError(f"failed to read prefabs: {prefabs_path}: {exc}") from exc
    if not isinstance(prefabs_payload, list):
        raise StampReportError(f"prefabs payload must be a list: {prefabs_path}")
    known_prefabs: set[str] = {
        str(entry.get("id")) for entry in prefabs_payload if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }

    stamp_entities_value = stamp_payload.get("entities", [])
    if stamp_entities_value is None:
        stamp_entities_value = []
    if not isinstance(stamp_entities_value, list):
        raise StampReportError("stamp.entities must be an array when provided")

    for idx, entry in enumerate(stamp_entities_value):
        if not isinstance(entry, dict):
            raise StampReportError(f"stamp.entities[{idx}] must be an object")
        prefab_id = entry.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            raise StampReportError(f"stamp.entities[{idx}].prefab_id must be a non-empty string")
        if prefab_id.strip() not in known_prefabs:
            raise StampReportError(f"stamp.entities[{idx}] prefab_id not found: {prefab_id}")

    tile_size = _tilemap_try_resolve_tile_size_for_stamp(scene_path=resolved_scene_path, tilemap=tilemap)

    tile_changes_by_layer: dict[str, dict[int, tuple[int, int]]] = {}

    stamp_tiles_value = stamp_payload.get("tiles", [])
    if stamp_tiles_value is None:
        stamp_tiles_value = []
    if not isinstance(stamp_tiles_value, list):
        raise StampReportError("stamp.tiles must be an array when provided")

    tiles_cache: dict[str, list[int]] = {}

    for idx, entry in enumerate(stamp_tiles_value):
        if not isinstance(entry, dict):
            raise StampReportError(f"stamp.tiles[{idx}] must be an object")

        layer_id = entry.get("layer_id")
        if not isinstance(layer_id, str) or not layer_id.strip():
            raise StampReportError(f"stamp.tiles[{idx}].layer_id must be a non-empty string")
        layer_id = layer_id.strip()

        try:
            rel_x = int(cast(Any, entry.get("x")))
            rel_y = int(cast(Any, entry.get("y")))
            w = int(cast(Any, entry.get("w")))
            h = int(cast(Any, entry.get("h")))
            tile = int(cast(Any, entry.get("tile")))
        except Exception as exc:
            raise StampReportError(f"stamp.tiles[{idx}] x/y/w/h/tile must be integers") from exc

        if w <= 0 or h <= 0:
            raise StampReportError(f"stamp.tiles[{idx}] w/h must be > 0")
        if rel_x < 0 or rel_y < 0 or rel_x + w > stamp_w or rel_y + h > stamp_h:
            raise StampReportError(f"stamp.tiles[{idx}] rect out of stamp bounds")

        x0 = origin_x + rel_x
        y0 = origin_y + rel_y
        x1 = x0 + w - 1
        y1 = y0 + h - 1

        try:
            layer = get_layer_by_id(tile_layers, layer_id)
        except KeyError as exc:
            raise StampReportError(f"tile layer not found: {layer_id}") from exc

        if layer_id not in tiles_cache:
            tiles_cache[layer_id] = ensure_tiles_array(layer, dims=dims)

        tiles = tiles_cache[layer_id]
        if x0 < 0 or y0 < 0 or x1 >= dims.width or y1 >= dims.height:
            raise StampReportError(f"stamp tile rect out of bounds for layer '{layer_id}': rect out of bounds")

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
    warnings: list[str] = []
    for idx, entry in enumerate(stamp_entities_value):
        if not isinstance(entry, dict):
            continue
        prefab_id = str(entry.get("prefab_id") or "").strip()
        id_suffix = entry.get("id_suffix")
        if not isinstance(id_suffix, str) or not id_suffix.strip():
            raise StampReportError(f"stamp.entities[{idx}].id_suffix must be a non-empty string")
        id_suffix = id_suffix.strip()
        try:
            rel_x = int(cast(Any, entry.get("x")))
            rel_y = int(cast(Any, entry.get("y")))
        except Exception as exc:
            raise StampReportError(f"stamp.entities[{idx}].x/y must be integers") from exc
        if rel_x < 0 or rel_y < 0 or rel_x >= stamp_w or rel_y >= stamp_h:
            raise StampReportError(f"stamp.entities[{idx}] position out of stamp bounds")

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
            msg = f"prefab_mismatch: {entity_id} (expected {prefab_id}, got {existing.get('prefab_id')})"
            if ignore_prefab_mismatch:
                warnings.append(msg)
                continue
            raise StampReportError(msg)

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
        "warnings": warnings,
    }
