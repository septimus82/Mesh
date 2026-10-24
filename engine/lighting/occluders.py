from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from engine.geometry_tools import sanitize_poly
from engine.paths import resolve_path


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


@dataclass(slots=True)
class OccluderCache:
    """
    Tiny deterministic cache keyed by (scene_path, revision).

    Intended for per-scene collision occluders derived from tilemap data; callers
    should pass a monotonic revision (e.g. window.scene_dirty_counter) and call
    invalidate() on reload.
    """

    scene_path: str | None = None
    revision: int = -1
    value: Optional[list[dict[str, Any]]] = None

    def invalidate(self) -> None:
        self.scene_path = None
        self.revision = -1
        self.value = None

    def get_or_build(
        self, *, scene_path: str | None, revision: int, build: Callable[[], list[dict[str, Any]]]
    ) -> list[dict[str, Any]]:
        key = str(scene_path or "").strip() or None
        if key is None:
            self.invalidate()
            return []
        if self.scene_path == key and self.revision == int(revision) and self.value is not None:
            return self.value
        self.scene_path = key
        self.revision = int(revision)
        self.value = build()
        return self.value


OCCLUDER_CACHE = OccluderCache()


def build_occluders_from_tile_layer(
    layer_grid: Sequence[Sequence[int]],
    tile_size: int | tuple[int, int],
) -> list[Rect]:
    """
    Merge non-zero tiles in a layer into a deterministic list of world-space rects.

    The input grid is assumed to be Tiled-style row-major with y=0 as the top row.
    """
    if isinstance(tile_size, tuple):
        tile_w, tile_h = int(tile_size[0]), int(tile_size[1])
    else:
        tile_w, tile_h = int(tile_size), int(tile_size)

    height = len(layer_grid)
    width = len(layer_grid[0]) if height else 0
    if width <= 0 or height <= 0:
        return []

    for row in layer_grid:
        if len(row) != width:
            raise ValueError("layer_grid is not rectangular")

    @dataclass
    class _Active:
        x0: int
        x1: int
        y0: int  # start row index (top-based)
        h: int

    rects: list[_Active] = []
    active: dict[tuple[int, int], _Active] = {}

    for y in range(height):
        row = layer_grid[y]
        segments: list[tuple[int, int]] = []
        x = 0
        while x < width:
            if int(row[x]) == 0:
                x += 1
                continue
            x0 = x
            while x < width and int(row[x]) != 0:
                x += 1
            segments.append((x0, x - 1))

        new_active: dict[tuple[int, int], _Active] = {}
        for seg in segments:
            prev = active.get(seg)
            if prev is None:
                new_active[seg] = _Active(x0=seg[0], x1=seg[1], y0=y, h=1)
            else:
                prev.h += 1
                new_active[seg] = prev

        for seg in sorted(active.keys()):
            if seg not in new_active:
                rects.append(active[seg])

        active = new_active

    for seg in sorted(active.keys()):
        rects.append(active[seg])

    out: list[Rect] = []
    for r in rects:
        rect_w_tiles = r.x1 - r.x0 + 1
        rect_h_tiles = r.h
        world_x = r.x0 * tile_w
        world_y = (height - r.y0 - rect_h_tiles) * tile_h
        out.append(
            Rect(
                x=float(world_x),
                y=float(world_y),
                width=float(rect_w_tiles * tile_w),
                height=float(rect_h_tiles * tile_h),
            )
        )

    out.sort(key=lambda rr: (rr.y, rr.x, rr.height, rr.width))
    return out


def _inline_collision_layer(tilemap_cfg: Mapping[str, Any], layer_id: str) -> dict[str, Any] | None:
    """The scene's own collision layer (``tile_layers``), in the Tiled shape the builder below reads."""
    layers = tilemap_cfg.get("tile_layers")
    if not layer_id or not isinstance(layers, list):
        return None
    layer = next((entry for entry in layers if isinstance(entry, Mapping) and entry.get("id") == layer_id), None)
    tiles = layer.get("tiles") if layer is not None else None
    if not isinstance(tiles, list):
        return None
    return {key: tilemap_cfg.get(key) for key in ("width", "height", "tilewidth", "tileheight")} | {
        "layers": [{"type": "tilelayer", "name": layer_id, "data": tiles}]}


# --- the shape of a wall tile (Milestone 12.2) -----------------------------------------------------------------
# A rock, a bush or a tree painted on the walls layer blocks its whole tile, but its picture is round: cast as the
# whole tile it threw a square shadow. A mostly see-through tile casts the outline of what is drawn on it instead
# (a few-sided convex outline: shadows stay cheap). A tile its tileset marks ``casts_shadow: false`` (water)
# casts none. Solid tiles cast as before: whole tiles, merged with their neighbours.
FULL_TILE = 0.9  # this share of a tile's pixels drawn: it casts as the whole tile
OUTLINE_POINTS = 12  # an outline's corners at most
GID_MASK = 0x1FFFFFFF  # Tiled keeps flip flags in a gid's top bits
_TILESET_SHAPES: dict[tuple[str, float], dict[int, list[tuple[float, float]] | None]] = {}


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    upper: list[tuple[float, float]] = []
    for pt in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], pt) <= 0:
            lower.pop()
        lower.append(pt)
    for pt in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], pt) <= 0:
            upper.pop()
        upper.append(pt)
    return lower[:-1] + upper[:-1]


def _fewer_corners(poly: list[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    """Drop the corners that matter least (the smallest triangle with their neighbours) down to ``limit``."""
    poly = list(poly)
    while len(poly) > limit:
        n = len(poly)
        areas = [abs((poly[i][0] - poly[i - 1][0]) * (poly[(i + 1) % n][1] - poly[i - 1][1])
                     - (poly[(i + 1) % n][0] - poly[i - 1][0]) * (poly[i][1] - poly[i - 1][1])) for i in range(n)]
        del poly[areas.index(min(areas))]
    return poly


def _tileset_shapes(tileset_file: Path) -> dict[int, list[tuple[float, float]] | None]:
    """Local tile id -> its outline (tile pixels, x right, y up from the tile's bottom) or None (no shadow).
    Tiles not listed cast as the whole tile. Cached per tileset file and change time."""
    try:
        key = (str(tileset_file), tileset_file.stat().st_mtime)
    except OSError:
        return {}
    if key in _TILESET_SHAPES:
        return _TILESET_SHAPES[key]
    shapes: dict[int, list[tuple[float, float]] | None] = {}
    try:
        from PIL import Image  # noqa: PLC0415

        data = json.loads(tileset_file.read_text(encoding="utf-8"))
        tw, th = int(data["tilewidth"]), int(data["tileheight"])
        columns, margin, spacing = int(data["columns"]), int(data.get("margin") or 0), int(data.get("spacing") or 0)
        alpha = Image.open(tileset_file.parent / str(data["image"])).convert("RGBA").getchannel("A")
        count = int(data.get("tilecount") or columns * ((alpha.height - margin + spacing) // (th + spacing)))
    except (OSError, ValueError, KeyError, TypeError):
        _TILESET_SHAPES[key] = shapes
        return shapes
    no_shadow = {int(t.get("id", -1)) for t in data.get("tiles") or [] if isinstance(t, dict)
                 and any(isinstance(prop, dict) and prop.get("name") == "casts_shadow" and prop.get("value") is False
                         for prop in t.get("properties") or [])}
    for lid in range(count):
        if lid in no_shadow:
            shapes[lid] = None
            continue
        x0, y0 = margin + (lid % columns) * (tw + spacing), margin + (lid // columns) * (th + spacing)
        cells = list(alpha.crop((x0, y0, x0 + tw, y0 + th)).getdata())
        drawn = [(i % tw, i // tw) for i, value in enumerate(cells) if value > 128]
        if len(drawn) >= FULL_TILE * tw * th:
            continue
        if not drawn:
            shapes[lid] = None
            continue
        corners = [(float(x + dx), float(th - y - dy)) for x, y in drawn for dx in (0, 1) for dy in (0, 1)]
        shapes[lid] = _fewer_corners(_convex_hull(corners), OUTLINE_POINTS)
    _TILESET_SHAPES[key] = shapes
    return shapes


def tile_shapes(tilemap_cfg: Mapping[str, Any], scene_path: str | None) -> dict[int, list[tuple[float, float]] | None]:
    """gid -> how that tile casts (see _tileset_shapes), from the map file's tilesets. Empty when the map or its
    tilesets can't be found: every wall tile then casts as the whole tile, as before."""
    map_rel = str(tilemap_cfg.get("path") or "").strip()
    if not map_rel or not scene_path:
        return {}
    candidates = [resolve_path(str(scene_path)).parent / map_rel, resolve_path(map_rel)]
    map_file = next((c for c in candidates if c.is_file()), None)
    if map_file is None:
        return {}
    try:
        tilesets = json.loads(map_file.read_text(encoding="utf-8")).get("tilesets") or []
    except (OSError, ValueError):
        return {}
    out: dict[int, list[tuple[float, float]] | None] = {}
    for entry in tilesets:
        if not isinstance(entry, dict) or not entry.get("source"):
            continue
        first = int(entry.get("firstgid") or 1)
        for lid, shape in _tileset_shapes((map_file.parent / str(entry["source"])).resolve()).items():
            out[first + lid] = shape
    return out


def build_occluders_from_scene_payload(
    scene_payload: Mapping[str, Any],
    *,
    scene_path: str | None = None,
    revision: int = 0,
) -> list[dict[str, Any]]:
    """
    Best-effort collision occluders derived from the scene's tilemap collision layer.

    Returns occluder configs compatible with LightManager.configure_scene_occluders:
      {"id","type","x","y","width","height"}.

    Does not add occluders if the scene does not specify a tilemap collision layer.
    """

    def _build() -> list[dict[str, Any]]:
        occluders: list[dict[str, Any]] = []

        tilemap_cfg = scene_payload.get("tilemap")
        if isinstance(tilemap_cfg, Mapping):
            collision_layer_id = str(tilemap_cfg.get("collision_layer_id") or "").strip()
            tilemap_path = str(tilemap_cfg.get("path") or "").strip()
            inline = _inline_collision_layer(tilemap_cfg, collision_layer_id)
            if inline is not None:  # Mesh Studio's maps: the layers are in the scene, the map file holds tilesets
                tilemap_data: Any = inline
            elif collision_layer_id and tilemap_path:
                tilemap_file = resolve_path(tilemap_path)
                try:
                    tilemap_data = json.loads(tilemap_file.read_text(encoding="utf-8"))
                except Exception:
                    tilemap_data = None
            else:
                tilemap_data = None
            if collision_layer_id:
                if isinstance(tilemap_data, dict):
                    width = int(tilemap_data.get("width") or 0)
                    height = int(tilemap_data.get("height") or 0)
                    tile_w = int(tilemap_data.get("tilewidth") or 0)
                    tile_h = int(tilemap_data.get("tileheight") or 0)

                    if width > 0 and height > 0 and tile_w > 0 and tile_h > 0:
                        layers = tilemap_data.get("layers")
                        layer_data: list[int] | None = None
                        if isinstance(layers, list):
                            for layer in layers:
                                if not isinstance(layer, dict):
                                    continue
                                if layer.get("type") != "tilelayer":
                                    continue
                                if str(layer.get("name") or "") != collision_layer_id:
                                    continue
                                data = layer.get("data")
                                if isinstance(data, list) and len(data) == width * height:
                                    layer_data = [int(v or 0) for v in data]
                                break

                        if layer_data is not None:
                            overrides = tilemap_cfg.get("overrides")
                            if isinstance(overrides, Mapping):
                                layers_override = overrides.get("layers")
                                if isinstance(layers_override, Mapping):
                                    override_data = layers_override.get(collision_layer_id)
                                    if isinstance(override_data, list) and len(override_data) == width * height:
                                        layer_data = [int(v or 0) for v in override_data]

                            grid = [layer_data[y * width : (y + 1) * width] for y in range(height)]
                            shapes = tile_shapes(tilemap_cfg, scene_path)
                            if shapes:  # see-through tiles cast their outline, one each; solid ones merge as before
                                for row_i, row in enumerate(grid):
                                    for col_i, gid in enumerate(row):
                                        outline = shapes.get(int(gid) & GID_MASK, ()) if gid else ()
                                        if not outline:
                                            continue
                                        bx, by = col_i * tile_w, (height - row_i - 1) * tile_h
                                        occluders.append({"id": f"auto_{collision_layer_id}_tile_{bx}_{by}", "type": "poly",
                                                          "points": [(bx + px, by + py) for px, py in outline]})
                                grid = [[0 if gid and (int(gid) & GID_MASK) in shapes else gid for gid in row] for row in grid]
                            rects = build_occluders_from_tile_layer(grid, (tile_w, tile_h))

                            for r in rects:
                                rid = f"auto_{collision_layer_id}_{int(r.x)}_{int(r.y)}_{int(r.width)}_{int(r.height)}"
                                occluders.append(
                                    {
                                        "id": rid,
                                        "type": "rect",
                                        "x": float(r.x),
                                        "y": float(r.y),
                                        "width": float(r.width),
                                        "height": float(r.height),
                                    }
                                )

        def _occ_sort_key(o: dict[str, Any]) -> tuple:
            if o.get("type") == "poly":
                pts = o.get("points") or []
                flat = tuple(c for p in pts for c in p) if isinstance(pts, list) else ()
                return (o.get("id", ""), "poly", flat)
            return (
                o.get("id", ""),
                "rect",
                float(o.get("x", 0.0)),
                float(o.get("y", 0.0)),
                float(o.get("width", 0.0)),
                float(o.get("height", 0.0)),
            )

        occluders.sort(key=_occ_sort_key)
        return occluders

    return OCCLUDER_CACHE.get_or_build(scene_path=scene_path, revision=revision, build=_build)


def build_entity_occluders_from_scene_payload(scene_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    occluders: list[dict[str, Any]] = []
    entities = scene_payload.get("entities")
    if not isinstance(entities, list):
        return occluders

    for index, entity in enumerate(entities):
        if not isinstance(entity, Mapping):
            continue
        points = entity.get("occluder_poly")
        if not isinstance(points, list):
            continue
        local_points = sanitize_poly(points)
        if not local_points:
            continue
        try:
            base_x = float(entity.get("x", 0.0))
            base_y = float(entity.get("y", 0.0))
        except Exception:  # noqa: BLE001  # REASON: malformed occluder base positions should fall back to origin offsets for that entity only
            base_x = 0.0
            base_y = 0.0
        name = (
            entity.get("id")
            or entity.get("name")
            or entity.get("mesh_name")
            or f"entity_{index}"
        )
        cache_key = (
            str(name),
            float(base_x),
            float(base_y),
            tuple(local_points),
        )
        cached = _ENTITY_OCCLUDER_CACHE.get(cache_key)
        if cached is None:
            cached = _convert_poly_to_world(local_points, base_x, base_y)
            _ENTITY_OCCLUDER_CACHE[cache_key] = cached
        occ_id = f"{name}_occluder_poly"
        occluders.append({"id": occ_id, "type": "poly", "points": cached})

    occluders.sort(
        key=lambda o: (o.get("id", ""), tuple(c for p in o.get("points", []) for c in p)),
    )
    return occluders


def _convert_poly_to_world(
    points: list[tuple[float, float]], base_x: float, base_y: float
) -> list[tuple[float, float]]:
    return [(base_x + px, base_y + py) for px, py in points]


_ENTITY_OCCLUDER_CACHE: dict[
    tuple[str, float, float, tuple[tuple[float, float], ...]],
    list[tuple[float, float]],
] = {}


def reset_entity_occluder_cache() -> None:
    _ENTITY_OCCLUDER_CACHE.clear()
