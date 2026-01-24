from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from engine.paths import resolve_path
from engine.geometry_tools import sanitize_poly


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
            if collision_layer_id and tilemap_path:
                tilemap_file = resolve_path(tilemap_path)
                try:
                    tilemap_data = json.loads(tilemap_file.read_text(encoding="utf-8"))
                except Exception:
                    tilemap_data = None

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
        except Exception:  # noqa: BLE001
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
