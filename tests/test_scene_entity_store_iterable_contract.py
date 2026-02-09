from __future__ import annotations

from dataclasses import dataclass

from engine.scene_entity_store_controller import SceneEntityStoreController


@dataclass
class _FakeSprite:
    mesh_name: str


class _FakeScene:
    def __init__(self, sprites: list[_FakeSprite]) -> None:
        self.all_sprites = sprites


def test_scene_entity_store_iterable_attached_controller() -> None:
    sprites = [_FakeSprite("a"), _FakeSprite("b")]
    scene = _FakeScene(sprites)
    store = SceneEntityStoreController(scene)

    assert list(store) == sprites
    assert len(store) == len(sprites)
    assert store.iter_entities(scene) == sprites


def test_scene_entity_store_iterable_without_controller_is_empty() -> None:
    store = SceneEntityStoreController()
    assert list(store) == []
    assert len(store) == 0
    assert store.iter_entities() == []
