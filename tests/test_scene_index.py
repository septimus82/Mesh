from __future__ import annotations

from unittest.mock import MagicMock

from engine.scene_index import SceneIndex


def _sprite_with_id(entity_id: str):
    sprite = MagicMock()
    sprite.mesh_entity_data = {"id": entity_id}
    sprite.mesh_name = None
    return sprite


def _sprite_with_mesh_name(name: str):
    sprite = MagicMock()
    sprite.mesh_entity_data = {}
    sprite.mesh_name = name
    return sprite


def _trigger_zone_sprite(*, entity_id: str, zone_id: str, mesh_name: str | None = None):
    sprite = MagicMock()
    sprite.mesh_name = mesh_name
    sprite.mesh_entity_data = {
        "id": entity_id,
        "behaviour_config": {"TriggerZone": {"zone_id": zone_id}},
    }
    return sprite


def test_scene_index_build_and_lookup() -> None:
    a = _sprite_with_id("a")
    b = _sprite_with_id("b")
    c = _sprite_with_id("c")

    idx = SceneIndex.build_from_sprites([a, b, c])

    assert idx.get_by_id("a") is a
    assert idx.get_by_id("b") is b
    assert idx.get_by_id("c") is c
    assert idx.get_by_id("missing") is None
    assert idx.duplicate_ids == []


def test_scene_index_duplicate_ids_keep_first_and_record_duplicates() -> None:
    first = _sprite_with_id("dup")
    second = _sprite_with_id("dup")
    third = _sprite_with_id("dup")

    idx = SceneIndex.build_from_sprites([first, second, third])

    assert idx.get_by_id("dup") is first
    assert idx.duplicate_ids == ["dup", "dup"]


def test_scene_index_mesh_name_indexing_and_duplicates_deterministic() -> None:
    first = _sprite_with_mesh_name("Anchor")
    second = _sprite_with_mesh_name("Anchor")
    third = _sprite_with_mesh_name("Other")

    idx = SceneIndex.build_from_sprites([first, second, third])

    # Lookup is case-insensitive (legacy behavior).
    assert idx.get_first_by_mesh_name("anchor") is first
    assert idx.get_first_by_mesh_name("ANCHOR") is first
    assert idx.by_mesh_name["anchor"] == [first, second]
    assert idx.duplicate_mesh_names == ["anchor"]


def test_scene_index_zone_id_indexing_and_duplicates_deterministic() -> None:
    first = _trigger_zone_sprite(entity_id="a", zone_id="ZoneA", mesh_name="Z")
    second = _trigger_zone_sprite(entity_id="b", zone_id="ZoneA", mesh_name="Z2")

    idx = SceneIndex.build_from_sprites([first, second])

    assert idx.get_by_zone_id("zonea") is first
    assert idx.duplicate_zone_ids == ["zonea"]
