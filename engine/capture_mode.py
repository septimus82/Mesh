from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from engine.tile_paint_mode import world_to_tile

CaptureMode = Literal["stamp", "brush"]
BrushFilterMode = Literal["nonzero", "tile", "all"]


@dataclass(slots=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    def normalized(self) -> "Rect":
        x0 = min(int(self.x0), int(self.x1))
        x1 = max(int(self.x0), int(self.x1))
        y0 = min(int(self.y0), int(self.y1))
        y1 = max(int(self.y0), int(self.y1))
        return Rect(x0=x0, y0=y0, x1=x1, y1=y1)

    @property
    def w(self) -> int:
        r = self.normalized()
        return int(r.x1 - r.x0 + 1)

    @property
    def h(self) -> int:
        r = self.normalized()
        return int(r.y1 - r.y0 + 1)


@dataclass(slots=True)
class CaptureState:
    enabled: bool = False
    mode: CaptureMode = "stamp"
    rect: Rect | None = None
    drag_anchor: tuple[int, int] | None = None
    include_entities: bool = True
    layer_id: str = ""
    brush_filter_mode: BrushFilterMode = "nonzero"
    brush_filter_value: int = 0


def normalize_rect(x0: int, y0: int, x1: int, y1: int) -> Rect:
    return Rect(x0=int(x0), y0=int(y0), x1=int(x1), y1=int(y1)).normalized()


def _iter_tile_layers(tilemap: Any) -> list[dict[str, Any]]:
    if not isinstance(tilemap, dict):
        return []
    raw = tilemap.get("tile_layers")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict):
            out.append(entry)
    return out


def iter_layer_ids_sorted_by_z_id(scene_payload: dict[str, Any]) -> list[str]:
    tilemap = scene_payload.get("tilemap")
    layers = _iter_tile_layers(tilemap)
    pairs: list[tuple[int, str]] = []
    for entry in layers:
        layer_id = entry.get("id")
        if not isinstance(layer_id, str) or not layer_id.strip():
            continue
        z_val = entry.get("z", -100)
        z = int(z_val) if isinstance(z_val, int) else (-100 if not isinstance(z_val, float) else int(z_val))
        pairs.append((z, layer_id.strip()))
    pairs.sort(key=lambda t: (int(t[0]), str(t[1])))
    return [layer_id for _z, layer_id in pairs]


def _get_layer_entry(scene_payload: dict[str, Any], layer_id: str) -> dict[str, Any] | None:
    wanted = str(layer_id or "").strip()
    if not wanted:
        return None
    tilemap = scene_payload.get("tilemap")
    for entry in _iter_tile_layers(tilemap):
        if entry.get("id") == wanted:
            return entry
    return None


def extract_tiles_in_rect(
    scene_payload: dict[str, Any],
    *,
    layer_id: str,
    rect: Rect,
    map_width: int,
    map_height: int,
) -> list[int]:
    r = rect.normalized()
    w = int(map_width)
    h = int(map_height)
    if w <= 0 or h <= 0:
        raise ValueError("map_width/map_height must be > 0")
    if r.x0 < 0 or r.y0 < 0 or r.x1 >= w or r.y1 >= h:
        raise IndexError("rect out of bounds")

    entry = _get_layer_entry(scene_payload, layer_id)
    tiles = entry.get("tiles") if isinstance(entry, dict) else None
    flat: list[int]
    if isinstance(tiles, list) and len(tiles) == w * h and all(isinstance(v, int) for v in tiles):
        flat = [int(v) for v in tiles]
    else:
        flat = [0] * (w * h)

    out: list[int] = []
    for yy in range(int(r.y0), int(r.y1) + 1):
        row_start = int(yy) * w
        for xx in range(int(r.x0), int(r.x1) + 1):
            out.append(int(flat[row_start + int(xx)]))
    return out


def _tiles_to_row_runs(tiles: list[int], *, w: int, h: int) -> list[tuple[int, int, int, int]]:
    runs: list[tuple[int, int, int, int]] = []
    for y in range(int(h)):
        row_start = int(y) * int(w)
        current = int(tiles[row_start])
        run_x0 = 0
        for x in range(1, int(w)):
            value = int(tiles[row_start + x])
            if value != current:
                runs.append((y, run_x0, x - run_x0, current))
                current = value
                run_x0 = x
        runs.append((y, run_x0, int(w) - run_x0, current))
    return runs


def build_stamp_payload(
    scene_payload: dict[str, Any],
    *,
    rect: Rect,
    map_width: int,
    map_height: int,
    tile_width: int | None,
    tile_height: int | None,
    include_entities: bool,
) -> dict[str, Any]:
    r = rect.normalized()
    w = r.w
    h = r.h
    stamp_id = f"capture_stamp_{w}x{h}"

    tiles_entries: list[dict[str, Any]] = []
    for layer_id in iter_layer_ids_sorted_by_z_id(scene_payload):
        extracted = extract_tiles_in_rect(scene_payload, layer_id=layer_id, rect=r, map_width=map_width, map_height=map_height)
        runs = _tiles_to_row_runs(extracted, w=w, h=h)
        for y, x0, run_w, tile in runs:
            tiles_entries.append(
                {
                    "layer_id": layer_id,
                    "x": int(x0),
                    "y": int(y),
                    "w": int(run_w),
                    "h": 1,
                    "tile": int(tile),
                }
            )

    entities_entries: list[dict[str, Any]] = []
    if include_entities and isinstance(tile_width, int) and isinstance(tile_height, int) and tile_width > 0 and tile_height > 0:
        entities = scene_payload.get("entities")
        if isinstance(entities, list):
            entities_entries = extract_entities_in_rect(
                entities,
                rect=r,
                map_width=map_width,
                map_height=map_height,
                tile_width=tile_width,
                tile_height=tile_height,
            )

    payload: dict[str, Any] = {
        "id": stamp_id,
        "width": int(w),
        "height": int(h),
        "tiles": tiles_entries,
    }
    if include_entities:
        payload["entities"] = entities_entries
    return payload


def build_brush_payload(
    scene_payload: dict[str, Any],
    *,
    rect: Rect,
    map_width: int,
    map_height: int,
    layer_id: str,
    filter_mode: BrushFilterMode,
    filter_value: int,
) -> dict[str, Any]:
    r = rect.normalized()
    w = r.w
    h = r.h
    brush_id = f"capture_brush_{w}x{h}"
    extracted = extract_tiles_in_rect(scene_payload, layer_id=layer_id, rect=r, map_width=map_width, map_height=map_height)

    mask_tile = -1
    rows: list[list[int]] = []
    for y in range(h):
        row: list[int] = []
        for x in range(w):
            value = int(extracted[y * w + x])
            if filter_mode == "all":
                row.append(value)
            elif filter_mode == "tile":
                row.append(value if value == int(filter_value) else mask_tile)
            else:  # nonzero
                row.append(value if value != 0 else mask_tile)
        rows.append(row)

    return {
        "id": brush_id,
        "w": int(w),
        "h": int(h),
        "mask_tile": int(mask_tile),
        "tiles": rows,
    }


def build_capture_payload(
    scene_payload: dict[str, Any],
    *,
    mode: CaptureMode,
    rect: Rect,
    map_width: int,
    map_height: int,
    tile_width: int | None,
    tile_height: int | None,
    include_entities: bool,
    layer_id: str,
    brush_filter_mode: BrushFilterMode,
    brush_filter_value: int,
) -> tuple[str, dict[str, Any]]:
    """Return (header, payload) for the current capture settings."""
    m = str(mode).strip().lower()
    if m == "brush":
        payload = build_brush_payload(
            scene_payload,
            rect=rect,
            map_width=int(map_width),
            map_height=int(map_height),
            layer_id=str(layer_id),
            filter_mode=brush_filter_mode,
            filter_value=int(brush_filter_value),
        )
        header = f"CAPTURE BRUSH id={payload.get('id')} {int(rect.w)}x{int(rect.h)} layer={layer_id} filter={brush_filter_mode}"
        return header, payload

    payload = build_stamp_payload(
        scene_payload,
        rect=rect,
        map_width=int(map_width),
        map_height=int(map_height),
        tile_width=tile_width,
        tile_height=tile_height,
        include_entities=bool(include_entities),
    )
    entity_count = len(payload.get("entities") or []) if isinstance(payload.get("entities"), list) else 0
    header = f"CAPTURE STAMP id={payload.get('id')} {int(rect.w)}x{int(rect.h)} entities={entity_count}"
    return header, payload


def extract_entities_in_rect(
    entities: Iterable[object],
    *,
    rect: Rect,
    map_width: int,
    map_height: int,
    tile_width: int,
    tile_height: int,
) -> list[dict[str, Any]]:
    r = rect.normalized()
    out: list[dict[str, Any]] = []
    used_suffixes: set[str] = set()

    for entry in entities:
        if not isinstance(entry, dict):
            continue
        prefab_id = entry.get("prefab_id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            continue
        x = entry.get("x")
        y = entry.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        hit = world_to_tile(
            map_width=int(map_width),
            map_height=int(map_height),
            tile_width=int(tile_width),
            tile_height=int(tile_height),
            world_x=float(x),
            world_y=float(y),
        )
        if hit is None:
            continue
        tx, ty = hit
        if tx < int(r.x0) or tx > int(r.x1) or ty < int(r.y0) or ty > int(r.y1):
            continue

        entity_id = entry.get("id")
        base_suffix = str(entity_id) if entity_id not in (None, "") else f"{prefab_id.strip()}_{tx}_{ty}"
        suffix = _sanitize_id_suffix(base_suffix)
        if not suffix:
            suffix = "entity"
        if suffix in used_suffixes:
            i = 2
            while f"{suffix}_{i}" in used_suffixes:
                i += 1
            suffix = f"{suffix}_{i}"
        used_suffixes.add(suffix)

        out.append(
            {
                "prefab_id": prefab_id.strip(),
                "x": int(tx - int(r.x0)),
                "y": int(ty - int(r.y0)),
                "id_suffix": suffix,
                "_src_id": str(entity_id) if entity_id is not None else "",
            }
        )

    out.sort(key=lambda e: (str(e.get("prefab_id") or ""), str(e.get("_src_id") or ""), int(e.get("x") or 0), int(e.get("y") or 0)))
    for e in out:
        e.pop("_src_id", None)
    return out


def _sanitize_id_suffix(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    out: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-"}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_")
