"""
Runtime adapter for physics facade.
Connects pure physics_model to Arcade/SceneController state.
"""
from __future__ import annotations

from typing import Any, List, Tuple, Optional
from dataclasses import dataclass
from hashlib import md5

import engine.optional_arcade as optional_arcade
from engine.logging_tools import get_logger
from engine.physics_model import (
    Aabb,
    Circle,
    MoveRequest,
    MoveResult,
    circle_aabb_overlap,
    circle_circle_overlap,
    sweep_axis_separate,
)
from engine.swallowed_exceptions import _log_swallow
from engine.spatial_hash_model import SpatialHashConfig, SpatialHashIndex, build_spatial_hash, query_aabb
from engine.physics_broadphase_key_model import BroadphaseKeyInputs, compute_broadphase_cache_key

logger = get_logger(__name__)


class PhysicsProxySprite:
    """Minimal sprite-like object for Arcade collision queries."""
    def __init__(self, x: float, y: float, w: float, h: float):
        self.center_x = x
        self.center_y = y
        self.width = w
        self.height = h
        self.angle = 0.0
        # Some arcade versions check .position or ._hit_box_shape
        # We assume standard sprite behavior where center_x/y/width/height is enough for AABB check
        # if using Simple Hitbox.
        
    # Properties for AABB access if Arcade reads them directly
    @property
    def left(self): return self.center_x - self.width / 2
    @property
    def right(self): return self.center_x + self.width / 2
    @property
    def top(self): return self.center_y + self.height / 2
    @property
    def bottom(self): return self.center_y - self.height / 2

    # Setters needed if check_for_collision modifies it? (Unlikely for read-only query)

def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        _log_swallow("PHRT-001", "engine.physics_runtime blanket exception fallback")
        return float(default)


def _sprite_circle_shape(sprite: Any) -> Circle | None:
    cx = _as_float(getattr(sprite, "center_x", 0.0), 0.0)
    cy = _as_float(getattr(sprite, "center_y", 0.0), 0.0)

    # Lightweight direct attributes for tests/runtime stubs.
    kind_attr = str(getattr(sprite, "collider_kind", "") or "").strip().lower()
    if kind_attr == "circle":
        r = _as_float(getattr(sprite, "collider_radius", 0.0), 0.0)
        if r > 0.0:
            ox = _as_float(getattr(sprite, "collider_offset_x", 0.0), 0.0)
            oy = _as_float(getattr(sprite, "collider_offset_y", 0.0), 0.0)
            return Circle(cx + ox, cy + oy, r)

    # Entity-data collider component path used by scene entities.
    entity_data = getattr(sprite, "mesh_entity_data", None)
    if not isinstance(entity_data, dict):
        return None
    components = entity_data.get("components")
    if not isinstance(components, dict):
        return None
    collider = components.get("collider")
    if not isinstance(collider, dict):
        return None
    kind = str(collider.get("kind", "") or "").strip().lower()
    if kind != "circle":
        return None
    radius = _as_float(collider.get("r", collider.get("radius", 0.0)), 0.0)
    if radius <= 0.0:
        return None
    ox = _as_float(collider.get("offset_x", collider.get("ox", 0.0)), 0.0)
    oy = _as_float(collider.get("offset_y", collider.get("oy", 0.0)), 0.0)
    return Circle(cx + ox, cy + oy, radius)


def _sprite_to_shape(sprite: Any) -> Aabb | Circle:
    circle = _sprite_circle_shape(sprite)
    if circle is not None:
        return circle
    cx = _as_float(getattr(sprite, "center_x", 0.0), 0.0)
    cy = _as_float(getattr(sprite, "center_y", 0.0), 0.0)
    w = _as_float(getattr(sprite, "width", 0.0), 0.0)
    h = _as_float(getattr(sprite, "height", 0.0), 0.0)
    return Aabb(cx, cy, w, h)


def _shape_to_aabb(shape: Aabb | Circle) -> Aabb:
    if isinstance(shape, Circle):
        return shape.bounds()
    return shape


def _sprite_to_aabb(sprite: Any) -> Aabb:
    return _shape_to_aabb(_sprite_to_shape(sprite))


def _shapes_overlap(shape_a: Aabb | Circle, shape_b: Aabb | Circle) -> bool:
    if isinstance(shape_a, Circle) and isinstance(shape_b, Circle):
        return circle_circle_overlap((shape_a.x, shape_a.y), shape_a.radius, (shape_b.x, shape_b.y), shape_b.radius)
    if isinstance(shape_a, Circle):
        return circle_aabb_overlap((shape_a.x, shape_a.y), shape_a.radius, _shape_to_aabb(shape_b))
    if isinstance(shape_b, Circle):
        return circle_aabb_overlap((shape_b.x, shape_b.y), shape_b.radius, _shape_to_aabb(shape_a))
    return shape_a.intersection(shape_b) is not None

def _collider_sample_ids(solid_sprites: Any, *, limit: int = 8) -> tuple[int, ...]:
    if not solid_sprites:
        return ()
    ids: list[int] = []
    try:
        total = len(solid_sprites)
    except Exception:
        _log_swallow("PHRT-002", "engine.physics_runtime blanket exception fallback")
        total = 0
    sample_n = min(limit, max(0, total))
    for i in range(sample_n):
        try:
            obj = solid_sprites[i]
        except Exception:
            _log_swallow("PHRT-003", "engine.physics_runtime blanket exception fallback")
            break
        if hasattr(obj, "fake_id"):
            val = getattr(obj, "fake_id")
        elif hasattr(obj, "uid"):
            val = getattr(obj, "uid")
        elif hasattr(obj, "id"):
            val = getattr(obj, "id")
        else:
            val = id(obj)
        try:
            ids.append(int(val))
        except Exception:
            _log_swallow("PHRT-004", "engine.physics_runtime blanket exception fallback")
            ids.append(int(id(obj)))
    return tuple(ids)


def _collider_signature(obj: Any) -> int:
    left = getattr(obj, "left", None)
    right = getattr(obj, "right", None)
    bottom = getattr(obj, "bottom", None)
    top = getattr(obj, "top", None)
    if left is None or right is None or bottom is None or top is None:
        cx = getattr(obj, "center_x", None)
        cy = getattr(obj, "center_y", None)
        w = getattr(obj, "width", None)
        h = getattr(obj, "height", None)
        if cx is None or cy is None or w is None or h is None:
            return 0
        left = float(cx) - float(w) / 2.0
        right = float(cx) + float(w) / 2.0
        bottom = float(cy) - float(h) / 2.0
        top = float(cy) + float(h) / 2.0
    try:
        ql = int(round(float(left) * 4.0))
        qr = int(round(float(right) * 4.0))
        qb = int(round(float(bottom) * 4.0))
        qt = int(round(float(top) * 4.0))
    except Exception:
        _log_swallow("PHRT-005", "engine.physics_runtime blanket exception fallback")
        return 0
    sig = f"{ql}:{qr}:{qb}:{qt}"
    digest = md5(sig.encode("ascii")).hexdigest()[:8]
    return int(digest, 16)


def _collider_sample_sigs(solid_sprites: Any, *, limit: int = 8) -> tuple[int, ...]:
    if not solid_sprites:
        return ()
    sigs: list[int] = []
    try:
        total = len(solid_sprites)
    except Exception:
        _log_swallow("PHRT-006", "engine.physics_runtime blanket exception fallback")
        total = 0
    sample_n = min(limit, max(0, total))
    for i in range(sample_n):
        try:
            obj = solid_sprites[i]
        except Exception:
            _log_swallow("PHRT-007", "engine.physics_runtime blanket exception fallback")
            break
        sigs.append(_collider_signature(obj))
    return tuple(sigs)


def compute_runtime_broadphase_cache_key(
    *,
    scene_payload: Any = None,
    solid_sprites: Any = None,
    scene_path: str | None = None,
    collider_rev: int | None = None,
    collision_layer_id: str | None = None,
) -> str:
    path = str(scene_path or "")
    scene_identity: int | None = None
    if not path and scene_payload is not None:
        path = str(getattr(scene_payload, "scene_path", "") or "")
        if not path and isinstance(scene_payload, dict):
            path = str(scene_payload.get("scene_path", "") or scene_payload.get("path", "") or "")
    if not path and scene_payload is not None:
        scene_identity = id(scene_payload)
    if scene_identity is None and solid_sprites is not None:
        # Tie cache lifetime to the concrete collider collection object to
        # avoid stale reuse across different scene lists with similar samples.
        scene_identity = id(solid_sprites)
    count = 0
    if solid_sprites:
        try:
            count = len(solid_sprites)
        except Exception:
            _log_swallow("PHRT-008", "engine.physics_runtime blanket exception fallback")
            count = 0
    inp = BroadphaseKeyInputs(
        scene_path=path or None,
        scene_identity=scene_identity,
        collider_count=int(count),
        collider_id_sample=_collider_sample_ids(solid_sprites),
        collider_sig_sample=_collider_sample_sigs(solid_sprites),
        collider_rev=collider_rev,
        collision_layer_id=collision_layer_id,
    )
    return compute_broadphase_cache_key(inp)


class _BroadphaseCache:
    def __init__(self, cell_size_px: int = 32) -> None:
        self.cfg = SpatialHashConfig(cell_size_px=int(cell_size_px))
        self._index: Optional[SpatialHashIndex] = None
        self._sprites: list[Any] = []
        self._cache_key: str | None = None
        self._source_sprites_obj: Any = None
        self.build_count: int = 0
        self.perf_enabled: bool = False
        self.candidate_count: int = 0
        self.exact_checks_count: int = 0
        self.last_candidate_count: int = 0
        self.last_exact_checks_count: int = 0

    def reset(self) -> None:
        self._index = None
        self._sprites = []
        self._cache_key = None
        self._source_sprites_obj = None
        self.build_count = 0
        self.candidate_count = 0
        self.exact_checks_count = 0
        self.last_candidate_count = 0
        self.last_exact_checks_count = 0

    def enable_perf(self, enabled: bool) -> None:
        self.perf_enabled = bool(enabled)
        self.candidate_count = 0
        self.exact_checks_count = 0
        self.last_candidate_count = 0
        self.last_exact_checks_count = 0

    def reset_counters(self) -> None:
        self.candidate_count = 0
        self.exact_checks_count = 0
        self.last_candidate_count = 0
        self.last_exact_checks_count = 0

    def _build(self, solid_sprites: Any, cache_key: str) -> None:
        sprites = list(solid_sprites) if solid_sprites else []
        self._sprites = sprites
        self._index = build_spatial_hash(sprites, _sprite_to_aabb, self.cfg)
        self._cache_key = cache_key
        self._source_sprites_obj = solid_sprites
        self.build_count += 1

    def get_candidates(self, aabb: Aabb, solid_sprites: Any, cache_key: str) -> list[Any]:
        if not solid_sprites:
            self.last_candidate_count = 0
            return []
        if self._index is None or self._cache_key != cache_key or self._source_sprites_obj is not solid_sprites:
            self._build(solid_sprites, cache_key)
        if self._index is None:
            self.last_candidate_count = 0
            return []
        ids = query_aabb(self._index, aabb)
        self.last_candidate_count = len(ids)
        if self.perf_enabled:
            self.candidate_count += len(ids)
        return [self._sprites[i] for i in ids if 0 <= i < len(self._sprites)]


_BROADPHASE_CACHE = _BroadphaseCache()
_BROADPHASE_ENABLED = True
_LAST_SOLID_SPRITES: list[Any] = []


def _increment_perf_counter(name: str, delta: int = 1) -> None:
    try:
        getter = getattr(optional_arcade.arcade, "get_window", None)
        if not callable(getter):
            return
        window = getter()
        perf_stats = getattr(window, "perf_stats", None)
        add_counter = getattr(perf_stats, "add_counter", None)
        if callable(add_counter):
            add_counter(str(name), int(delta))
    except Exception:
        _log_swallow("PHRT-009", "engine.physics_runtime blanket exception fallback")
        return


def set_broadphase_enabled(enabled: bool) -> None:
    global _BROADPHASE_ENABLED
    _BROADPHASE_ENABLED = bool(enabled)


def enable_broadphase_counters(enabled: bool = True) -> None:
    _BROADPHASE_CACHE.enable_perf(enabled)

def reset_broadphase_counters() -> None:
    _BROADPHASE_CACHE.reset_counters()

def get_broadphase_stats() -> dict[str, int | bool]:
    return {
        "enabled": bool(_BROADPHASE_ENABLED),
        "build_count": int(_BROADPHASE_CACHE.build_count),
        "candidate_count": int(_BROADPHASE_CACHE.last_candidate_count),
        "exact_checks_count": int(_BROADPHASE_CACHE.last_exact_checks_count),
    }


def reset_broadphase_cache() -> None:
    _BROADPHASE_CACHE.reset()


def _sprite_entity_id(sprite: Any) -> str:
    for key in ("mesh_id", "entity_id", "id", "name"):
        value = getattr(sprite, key, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(data, dict):
        for key in ("id", "name"):
            value = data.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
    cx = _as_float(getattr(sprite, "center_x", 0.0), 0.0)
    cy = _as_float(getattr(sprite, "center_y", 0.0), 0.0)
    w = _as_float(getattr(sprite, "width", 0.0), 0.0)
    h = _as_float(getattr(sprite, "height", 0.0), 0.0)
    return f"unnamed:{cx:.4f}:{cy:.4f}:{w:.4f}:{h:.4f}"


def _sprite_is_sensor(sprite: Any) -> bool:
    if bool(getattr(sprite, "is_sensor", False)):
        return True
    if getattr(sprite, "sensor_id", None) is not None:
        return True
    data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(data, dict):
        tags = data.get("tags")
        if isinstance(tags, (list, tuple)) and any(str(tag).strip().lower() == "sensor" for tag in tags):
            return True
    return False


def _sprite_layer(sprite: Any) -> str | None:
    for key in ("mesh_layer", "layer_name", "layer", "collision_layer_id"):
        value = getattr(sprite, key, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(data, dict):
        for key in ("layer", "collision_layer_id"):
            value = data.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
    return None


def query_overlaps_circle(
    center_x: float,
    center_y: float,
    radius: float,
    *,
    include_sensors: bool = True,
    include_solids: bool = True,
    layers: Any = None,
) -> list[str]:
    """Query deterministic overlap IDs for a circle against known physics colliders.

    This uses broadphase AABB candidate filtering followed by circle-aware
    narrowphase checks (circle-circle, circle-aabb). The known collider set is
    the most recent solid-sprite collection seen by the physics runtime.
    """
    r = max(0.0, float(radius))
    if r <= 0.0:
        return []
    if not include_sensors and not include_solids:
        return []
    solids = list(_LAST_SOLID_SPRITES)
    if not solids:
        return []

    layer_filter: set[str] | None = None
    if layers is not None:
        try:
            layer_filter = {str(v).strip() for v in layers if str(v).strip()}
        except Exception:
            _log_swallow("PHRT-010", "engine.physics_runtime blanket exception fallback")
            layer_filter = None

    query_shape = Circle(float(center_x), float(center_y), r)
    query_bounds = query_shape.bounds()

    candidates: list[Any]
    if _BROADPHASE_ENABLED:
        cache_key = compute_runtime_broadphase_cache_key(solid_sprites=solids)
        candidates = _BROADPHASE_CACHE.get_candidates(query_bounds, solids, cache_key)
        if not candidates:
            candidates = solids
            _increment_perf_counter("physics.circle_query.fallback_full_scan.count", 1)
    else:
        candidates = solids

    matched_ids: set[str] = set()
    for sprite in candidates:
        is_sensor = _sprite_is_sensor(sprite)
        if is_sensor and not include_sensors:
            continue
        if (not is_sensor) and not include_solids:
            continue
        if layer_filter is not None:
            layer_name = _sprite_layer(sprite)
            if layer_name is None or layer_name not in layer_filter:
                continue
        try:
            if _shapes_overlap(query_shape, _sprite_to_shape(sprite)):
                matched_ids.add(_sprite_entity_id(sprite))
        except Exception:
            _log_swallow("PHRT-011", "engine.physics_runtime blanket exception fallback")
            continue
    return sorted(matched_ids)

def move_entity_with_physics(
    entity: Any,
    delta: Tuple[float, float],
    solid_sprites: Any, # optional_arcade.arcade.SpriteList
) -> MoveResult:
    """
    Execute a move using the deterministic physics model.
    Updates entity position in-place.
    Returns the result details.
    """
    global _LAST_SOLID_SPRITES
    _LAST_SOLID_SPRITES = list(solid_sprites) if solid_sprites else []

    # 1. Setup Request
    moving_shape = _sprite_to_shape(entity)
    start_aabb = _shape_to_aabb(moving_shape)
    moving_circle_radius = float(moving_shape.radius) if isinstance(moving_shape, Circle) else None
    req = MoveRequest(
        entity_id=getattr(entity, "mesh_id", "unknown"),
        from_pos=(start_aabb.x, start_aabb.y),
        delta=delta,
        aabb=start_aabb
    )
    
    # 2. Define Query Adapter
    check_collision = getattr(optional_arcade.arcade, "check_for_collision_with_list", None)
    
    def query_tiles(aabb: Aabb) -> List[Aabb]:
        if check_collision is None or not solid_sprites:
            _BROADPHASE_CACHE.last_candidate_count = 0
            _BROADPHASE_CACHE.last_exact_checks_count = 0
            return []

        # Create a proxy for the query at the HYPOTHETICAL position
        proxy = PhysicsProxySprite(aabb.x, aabb.y, aabb.w, aabb.h)

        candidates = solid_sprites
        used_broadphase_candidates = False
        if _BROADPHASE_ENABLED:
            cache_key = compute_runtime_broadphase_cache_key(solid_sprites=solid_sprites)
            candidates = _BROADPHASE_CACHE.get_candidates(aabb, solid_sprites, cache_key)
            used_broadphase_candidates = True
            # Broadphase is an optimization only; never allow false negatives.
            if not candidates:
                candidates = list(solid_sprites)
                used_broadphase_candidates = False
        else:
            try:
                _BROADPHASE_CACHE.last_candidate_count = len(candidates) if candidates else 0
            except Exception:
                _log_swallow("PHRT-012", "engine.physics_runtime blanket exception fallback")
                _BROADPHASE_CACHE.last_candidate_count = 0

        try:
            _BROADPHASE_CACHE.last_exact_checks_count = len(candidates) if candidates else 0
        except Exception:
            _log_swallow("PHRT-013", "engine.physics_runtime blanket exception fallback")
            _BROADPHASE_CACHE.last_exact_checks_count = 0

        if _BROADPHASE_CACHE.perf_enabled:
            _BROADPHASE_CACHE.exact_checks_count += _BROADPHASE_CACHE.last_exact_checks_count

        proxy_shape: Aabb | Circle
        if moving_circle_radius is not None and moving_circle_radius > 0.0:
            proxy_shape = Circle(aabb.x, aabb.y, moving_circle_radius)
        else:
            proxy_shape = aabb

        any_circle = isinstance(proxy_shape, Circle)
        if not any_circle:
            for candidate in candidates:
                if _sprite_circle_shape(candidate) is not None:
                    any_circle = True
                    break

        if any_circle:
            hits = []
            for s in candidates:
                try:
                    if _shapes_overlap(proxy_shape, _sprite_to_shape(s)):
                        hits.append(s)
                except Exception:
                    _log_swallow("PHRT-014", "engine.physics_runtime blanket exception fallback")
                    continue
        else:
            try:
                hits = check_collision(proxy, candidates)
            except TypeError:
                hits = []
                for s in candidates:
                    try:
                        if (
                            proxy.right > getattr(s, "left")
                            and proxy.left < getattr(s, "right")
                            and proxy.top > getattr(s, "bottom")
                            and proxy.bottom < getattr(s, "top")
                        ):
                            hits.append(s)
                    except Exception:
                        _log_swallow("PHRT-015", "engine.physics_runtime blanket exception fallback")
                        continue

        # Guard against stale broadphase candidate sets; if narrowed candidates
        # produced no hits, retry exact overlap on the full collider list.
        if not hits and used_broadphase_candidates:
            for s in solid_sprites:
                try:
                    if _shapes_overlap(proxy_shape, _sprite_to_shape(s)):
                        hits.append(s)
                except Exception:
                    _log_swallow("PHRT-016", "engine.physics_runtime blanket exception fallback")
                    continue

        return [_sprite_to_aabb(s) for s in hits]

    # 3. Execute Pure Model
    result = sweep_axis_separate(req, query_tiles)
    
    # 4. Apply Side Effects
    entity.center_x = result.final_pos[0]
    entity.center_y = result.final_pos[1]
    
    return result
