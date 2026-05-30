from __future__ import annotations

from types import SimpleNamespace

from engine.scene_entity_store_controller import SceneEntityStoreController


def test_entity_store_revision_and_drain() -> None:
    store = SceneEntityStoreController()
    assert store.revision == 0
    store.drain_pending(SimpleNamespace())
    assert store.revision == 0
    store.enqueue_op(SimpleNamespace(kind="spawn", payload=None, seq=0))
    store.drain_pending(SimpleNamespace(layers={}, solid_sprites=[]))
    assert store.revision == 1


def test_entity_store_iter_ids() -> None:
    store = SceneEntityStoreController()
    sprites = [
        SimpleNamespace(mesh_name="b"),
        SimpleNamespace(mesh_name="a"),
        SimpleNamespace(mesh_name=""),
    ]
    controller = SimpleNamespace(all_sprites=sprites)
    assert store.iter_entity_ids(controller) == ["a", "b"]


def test_entity_store_find_entity_prefers_first_by_name() -> None:
    store = SceneEntityStoreController()
    sprites = [
        SimpleNamespace(mesh_name="hero"),
        SimpleNamespace(mesh_name="hero"),
    ]
    controller = SimpleNamespace(all_sprites=sprites)
    assert store.find_entity(controller, "hero") is sprites[0]


def test_find_entity_int_in_range_returns_sprite() -> None:
    store = SceneEntityStoreController()
    sa, sb = SimpleNamespace(mesh_name="a"), SimpleNamespace(mesh_name="b")
    ctrl = SimpleNamespace(all_sprites=[sa, sb])
    assert store.find_entity(ctrl, 1) is sb


def test_find_entity_int_out_of_range_returns_none() -> None:
    store = SceneEntityStoreController()
    ctrl = SimpleNamespace(all_sprites=[SimpleNamespace(mesh_name="a")])
    assert store.find_entity(ctrl, 999) is None


def test_find_entity_negative_int_returns_none() -> None:
    store = SceneEntityStoreController()
    ctrl = SimpleNamespace(all_sprites=[SimpleNamespace(mesh_name="a")])
    assert store.find_entity(ctrl, -1) is None


def test_find_entity_name_hit_via_index() -> None:
    store = SceneEntityStoreController()
    s = SimpleNamespace(mesh_name="hero")
    ctrl = SimpleNamespace(all_sprites=[s])
    store.rebuild_index(ctrl)
    assert store.find_entity(ctrl, "hero") is s


def test_find_entity_name_hit_via_fallback_loop() -> None:
    # Index frozen empty so _index_by_name misses; fallback loop must find sprite.
    store = SceneEntityStoreController()
    s = SimpleNamespace(mesh_name="hero")
    ctrl = SimpleNamespace(all_sprites=[s])
    store._index_by_name = {}
    store._index_revision = store._revision  # prevent _ensure_index from rebuilding
    assert store.find_entity(ctrl, "hero") is s


def test_find_entity_unknown_name_returns_none() -> None:
    store = SceneEntityStoreController()
    ctrl = SimpleNamespace(all_sprites=[SimpleNamespace(mesh_name="a")])
    assert store.find_entity(ctrl, "ghost") is None


def test_find_entity_empty_identifier_returns_none() -> None:
    store = SceneEntityStoreController()
    ctrl = SimpleNamespace(all_sprites=[SimpleNamespace(mesh_name="a")])
    assert store.find_entity(ctrl, "") is None
    assert store.find_entity(ctrl, "   ") is None
