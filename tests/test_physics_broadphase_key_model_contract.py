from __future__ import annotations

from engine.physics_broadphase_key_model import BroadphaseKeyInputs, compute_broadphase_cache_key


def _inp(
    *,
    scene_path: str | None = None,
    scene_identity: int | None = None,
    collider_count: int = 0,
    collider_id_sample: tuple[int, ...] = (),
    collider_sig_sample: tuple[int, ...] = (),
    collider_rev: int | None = None,
    collision_layer_id: str | None = None,
) -> BroadphaseKeyInputs:
    return BroadphaseKeyInputs(
        scene_path=scene_path,
        scene_identity=scene_identity,
        collider_count=collider_count,
        collider_id_sample=collider_id_sample,
        collider_sig_sample=collider_sig_sample,
        collider_rev=collider_rev,
        collision_layer_id=collision_layer_id,
    )


def test_determinism_repeatable() -> None:
    inp = _inp(scene_path="scenes/a.json", collider_count=3, collider_id_sample=(1, 2, 3))
    keys = {compute_broadphase_cache_key(inp) for _ in range(50)}
    assert len(keys) == 1


def test_scene_path_priority() -> None:
    k1 = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", scene_identity=1, collider_count=1))
    k2 = compute_broadphase_cache_key(_inp(scene_path="scenes/b.json", scene_identity=1, collider_count=1))
    assert k1 != k2


def test_identity_fallback() -> None:
    k1 = compute_broadphase_cache_key(_inp(scene_path=None, scene_identity=1, collider_count=1))
    k2 = compute_broadphase_cache_key(_inp(scene_path=None, scene_identity=2, collider_count=1))
    assert k1 != k2


def test_collider_count_changes_key() -> None:
    k1 = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=1))
    k2 = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=2))
    assert k1 != k2


def test_sample_changes_key() -> None:
    k1 = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=2, collider_id_sample=(1, 2)))
    k2 = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=2, collider_id_sample=(1, 3)))
    assert k1 != k2


def test_optional_fields_included() -> None:
    base = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=1))
    with_rev = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=1, collider_rev=4))
    with_layer = compute_broadphase_cache_key(_inp(scene_path="scenes/a.json", collider_count=1, collision_layer_id="fg"))
    assert base != with_rev
    assert base != with_layer


def test_signature_sample_changes_key() -> None:
    k1 = compute_broadphase_cache_key(
        _inp(scene_path="scenes/a.json", collider_count=2, collider_id_sample=(1, 2), collider_sig_sample=(10, 20))
    )
    k2 = compute_broadphase_cache_key(
        _inp(scene_path="scenes/a.json", collider_count=2, collider_id_sample=(1, 2), collider_sig_sample=(10, 21))
    )
    assert k1 != k2


def test_signature_sample_order_affects_key() -> None:
    k1 = compute_broadphase_cache_key(
        _inp(scene_path="scenes/a.json", collider_count=2, collider_id_sample=(1, 2), collider_sig_sample=(10, 20))
    )
    k2 = compute_broadphase_cache_key(
        _inp(scene_path="scenes/a.json", collider_count=2, collider_id_sample=(1, 2), collider_sig_sample=(20, 10))
    )
    assert k1 != k2
