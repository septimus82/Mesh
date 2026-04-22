from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from engine.path_norm import normalize_scene_path
from engine.paths import resolve_path
from engine.scene_loader import SceneLoader
from engine.swallowed_exceptions import _log_swallow
from engine.tilemap_brush import Anchor, apply_brush, validate_brush
from engine.tilemap_edit import TilemapDims, ensure_tiles_array, get_layer_by_id


class BrushReportError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = int(exit_code)


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
            _log_swallow("BRUS-001", "engine/tooling_runtime/brush_report.py pass-only blanket swallow")
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


def compute_scene_brush_report(
    scene_payload: dict[str, Any],
    brush_payload: dict[str, Any],
    *,
    origin_x: int,
    origin_y: int,
    layer_id: str,
    anchor: Anchor = "tl",
    clip: bool = False,
) -> dict[str, Any]:
    """Compute a dry-run report of what `scene tilemap brush` would change (no writes)."""
    scene_path_display = str(scene_payload.get("_mesh_source_path") or "").strip()
    brush_path_raw = str(brush_payload.get("_mesh_source_path") or "").strip()

    try:
        brush = validate_brush(brush_payload)
    except Exception as exc:  # noqa: BLE001  # REASON: brush validation can raise mixed schema errors that should be wrapped into a single user-facing brush report failure
        raise BrushReportError(f"invalid brush JSON: {brush_path_raw}: {exc}") from exc

    loader = SceneLoader()
    scene = loader.apply_scene_defaults(dict(scene_payload))
    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict):
        raise BrushReportError(f"scene has no tilemap section: {scene_path_display}")

    resolved_scene_path = resolve_path(scene_path_display) if scene_path_display else Path.cwd()

    dims_raw = _tilemap_resolve_dims_for_edit(scene_path_display=scene_path_display, scene_path=resolved_scene_path, tilemap=tilemap)
    if dims_raw is None:
        raise BrushReportError("tilemap dims missing", exit_code=1)
    dims = TilemapDims(width=dims_raw[0], height=dims_raw[1])

    _scene_tilemap_maybe_migrate_layers(tilemap)
    tile_layers = tilemap.get("tile_layers")
    if not isinstance(tile_layers, list):
        raise BrushReportError(f"tilemap.tile_layers must be a list: {scene_path_display}")

    try:
        layer = get_layer_by_id(tile_layers, str(layer_id))
    except KeyError as exc:
        raise BrushReportError(f"tile layer not found: {layer_id}") from exc
    except Exception as exc:  # noqa: BLE001  # REASON: malformed layer metadata can raise mixed lookup errors and should be reported as a stable invalid-layer failure
        raise BrushReportError(f"invalid layer id: {exc}") from exc

    try:
        tiles = ensure_tiles_array(layer, dims=dims)
        new_tiles = apply_brush(
            list(tiles),
            width=int(dims.width),
            height=int(dims.height),
            x=int(origin_x),
            y=int(origin_y),
            brush=brush,
            anchor=anchor,
            clip=bool(clip),
        )
    except IndexError as exc:
        raise BrushReportError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001  # REASON: brush application normalizes mixed tile edit failures into a deterministic dry-run error result
        raise BrushReportError(f"failed to apply brush: {exc}") from exc

    tile_changes: list[dict[str, Any]] = []
    for idx, (before, after) in enumerate(zip(tiles, new_tiles, strict=False)):
        if int(before) == int(after):
            continue
        x = int(idx) % int(dims.width)
        y = int(idx) // int(dims.width)
        tile_changes.append(
            {
                "layer_id": str(layer_id),
                "x": int(x),
                "y": int(y),
                "before": int(before),
                "after": int(after),
            }
        )
    tile_changes.sort(key=lambda row: (row["layer_id"], int(row["y"]), int(row["x"])))

    return {
        "ok": True,
        "scene_path": normalize_scene_path(scene_path_display),
        "brush_path": normalize_scene_path(brush_path_raw),
        "layer_id": str(layer_id),
        "origin": {"x": int(origin_x), "y": int(origin_y)},
        "tile_changes": tile_changes,
    }
