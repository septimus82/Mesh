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
