from __future__ import annotations

from unittest.mock import MagicMock

from engine.scene_index import SceneIndex


def _sprite(*, entity_id=None, zone_id=None, mesh_name=None):
    sprite = MagicMock()
    sprite.mesh_name = mesh_name
    data = {}
    if entity_id is not None:
        data["id"] = entity_id
    if zone_id is not None:
        data["behaviour_config"] = {"TriggerZone": {"zone_id": zone_id}}
    sprite.mesh_entity_data = data
    return sprite


def test_scene_index_contract_case_insensitive_and_first_wins() -> None:
    # Intentionally mix casing/whitespace.
    first = _sprite(entity_id="  Player_01 ", zone_id=" ZoneA ", mesh_name="Anchor")
    dup_id = _sprite(entity_id="player_01", zone_id="ZoneB", mesh_name="ANCHOR")
    dup_zone = _sprite(entity_id="other", zone_id="zonea", mesh_name="anchor")

    idx = SceneIndex.build_from_sprites([first, dup_id, dup_zone])

    # Case-insensitive lookups.
    assert idx.get_by_id("PLAYER_01") is first
    assert idx.get_by_id(" player_01 ") is first

    assert idx.get_by_zone_id("ZONEA") is first
    assert idx.get_by_zone_id(" zonea ") is first

    assert idx.get_first_by_mesh_name("ANCHOR") is first
    assert idx.get_first_by_mesh_name(" anchor ") is first

    # Duplicate policy: first wins, duplicates recorded (normalized keys).
    assert idx.duplicate_ids == ["player_01"]
    assert idx.duplicate_zone_ids == ["zonea"]

    # Mesh name duplicates are recorded once per extra occurrence beyond first.
    assert idx.duplicate_mesh_names == ["anchor", "anchor"]
