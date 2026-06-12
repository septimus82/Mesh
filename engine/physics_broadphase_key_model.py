"""Pure model for physics broadphase cache keys."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BroadphaseKeyInputs:
    scene_path: str | None
    scene_identity: int | None
    collider_count: int
    collider_id_sample: tuple[int, ...]
    collider_sig_sample: tuple[int, ...] = ()
    collider_rev: int | None = None
    collision_layer_id: str | None = None


def compute_broadphase_cache_key(inp: BroadphaseKeyInputs) -> str:
    """Compute a deterministic, cheap cache key for broadphase reuse."""
    scene = str(inp.scene_path or "").strip()
    if scene:
        scene_part = f"path:{scene}"
    elif inp.scene_identity is not None:
        scene_part = f"id:{int(inp.scene_identity)}"
    else:
        scene_part = "unknown"

    parts = [
        "bp",
        scene_part,
        f"count:{int(inp.collider_count)}",
        "sample:" + ",".join(str(int(x)) for x in inp.collider_id_sample),
    ]
    if inp.collider_sig_sample:
        parts.append("sig:" + ",".join(str(int(x)) for x in inp.collider_sig_sample))
    if inp.collider_rev is not None:
        parts.append(f"rev:{int(inp.collider_rev)}")
    if inp.collision_layer_id is not None:
        parts.append(f"layer:{str(inp.collision_layer_id)}")
    return "|".join(parts)
