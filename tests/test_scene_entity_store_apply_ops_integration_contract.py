from __future__ import annotations

from types import SimpleNamespace

from engine.scene_entity_store_controller import SceneEntityStoreController


def test_apply_pending_ops_order_and_side_effects() -> None:
    store = SceneEntityStoreController()
    layers: dict[str, list[object]] = {"entities": []}
    solid_sprites: list[object] = []
    controller = SimpleNamespace(layers=layers, solid_sprites=solid_sprites)

    sprite_a = SimpleNamespace(mesh_tag=None)
    sprite_b = SimpleNamespace(mesh_tag=None)

    store.enqueue_mutation(sprite_a, x=1.0)
    store.enqueue_spawn(sprite_b, layer_name="entities", is_solid=True)
    store.enqueue_despawn(sprite_a)

    store.apply_pending_ops(controller, stage="test")

    assert sprite_b in layers["entities"]
    assert sprite_b in solid_sprites
    assert sprite_a not in layers["entities"]
    assert store.revision == 1


def test_apply_pending_ops_empty_no_change() -> None:
    store = SceneEntityStoreController()
    controller = SimpleNamespace(layers={}, solid_sprites=[])
    store.apply_pending_ops(controller, stage="empty")
    assert store.revision == 0
