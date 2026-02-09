"""
Runtime adapter for physics facade.
Connects pure physics_model to Arcade/SceneController state.
"""
from __future__ import annotations

from typing import Any, List, Tuple, Optional
from dataclasses import dataclass
from hashlib import md5

import engine.optional_arcade as optional_arcade
from engine.physics_model import Aabb, MoveRequest, MoveResult, sweep_axis_separate
from engine.spatial_hash_model import SpatialHashConfig, SpatialHashIndex, build_spatial_hash, query_aabb
from engine.physics_broadphase_key_model import BroadphaseKeyInputs, compute_broadphase_cache_key

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

def _sprite_to_aabb(sprite: Any) -> Aabb:
    # Handle both Arcade sprites and our own structs
    cx = getattr(sprite, "center_x", 0.0)
    cy = getattr(sprite, "center_y", 0.0)
    w = getattr(sprite, "width", 0.0)
    h = getattr(sprite, "height", 0.0)
    return Aabb(cx, cy, w, h)

def _collider_sample_ids(solid_sprites: Any, *, limit: int = 8) -> tuple[int, ...]:
    if not solid_sprites:
        return ()
    ids: list[int] = []
    try:
        total = len(solid_sprites)
    except Exception:
        total = 0
    sample_n = min(limit, max(0, total))
    for i in range(sample_n):
        try:
            obj = solid_sprites[i]
        except Exception:
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
        total = 0
    sample_n = min(limit, max(0, total))
    for i in range(sample_n):
        try:
            obj = solid_sprites[i]
        except Exception:
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
    count = 0
    if solid_sprites:
        try:
            count = len(solid_sprites)
        except Exception:
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
        self.build_count += 1

    def get_candidates(self, aabb: Aabb, solid_sprites: Any, cache_key: str) -> list[Any]:
        if not solid_sprites:
            self.last_candidate_count = 0
            return []
        if self._index is None or self._cache_key != cache_key:
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
    # 1. Setup Request
    start_aabb = _sprite_to_aabb(entity)
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
        if _BROADPHASE_ENABLED:
            cache_key = compute_runtime_broadphase_cache_key(solid_sprites=solid_sprites)
            candidates = _BROADPHASE_CACHE.get_candidates(aabb, solid_sprites, cache_key)
        else:
            try:
                _BROADPHASE_CACHE.last_candidate_count = len(candidates) if candidates else 0
            except Exception:
                _BROADPHASE_CACHE.last_candidate_count = 0

        try:
            _BROADPHASE_CACHE.last_exact_checks_count = len(candidates) if candidates else 0
        except Exception:
            _BROADPHASE_CACHE.last_exact_checks_count = 0

        if _BROADPHASE_CACHE.perf_enabled:
            _BROADPHASE_CACHE.exact_checks_count += _BROADPHASE_CACHE.last_exact_checks_count

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
                    continue

        return [_sprite_to_aabb(s) for s in hits]

    # 3. Execute Pure Model
    result = sweep_axis_separate(req, query_tiles)
    
    # 4. Apply Side Effects
    entity.center_x = result.final_pos[0]
    entity.center_y = result.final_pos[1]
    
    return result
