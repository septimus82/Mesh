from __future__ import annotations

from engine.editor_entity_ops import list_entities, update_entity_field


def test_list_entities_stable_ordering() -> None:
    scene = {
        "entities": [
            {"id": "b", "name": "Beta", "prefab_id": "npc", "x": 1, "y": 2},
            {"name": "Alpha", "prefab_id": "npc", "x": 3, "y": 4},
            "skip",
            {"mesh_name": "Charlie", "prefab_id": "boss", "x": 5, "y": 6},
        ]
    }

    summaries = list_entities(scene)
    assert [s.id for s in summaries] == ["b", "Alpha", "Charlie"]
    assert [s.name for s in summaries] == ["Beta", "Alpha", "Charlie"]
    assert [s.type for s in summaries] == ["npc", "npc", "boss"]


def test_update_entity_field_updates_scene_json_deterministically() -> None:
    scene = {"entities": [{"id": "a", "x": 1.0, "y": 2.0, "mesh_name": "Thing"}]}

    result = update_entity_field(scene, "a", "x", 3.5)
    assert result is scene
    assert scene["entities"][0]["x"] == 3.5
    assert scene["entities"][0]["y"] == 2.0

    update_entity_field(scene, "a", "mesh_name", "Widget")
    assert scene["entities"][0]["mesh_name"] == "Widget"


def test_rotation_wraps() -> None:
    scene = {"entities": [{"id": "a", "rotation": 0.0}]}

    update_entity_field(scene, "a", "rotation_deg", 370.0)
    assert scene["entities"][0]["rotation"] == 10.0

    update_entity_field(scene, "a", "rotation_deg", -10.0)
    assert scene["entities"][0]["rotation"] == 350.0


def test_tags_add_remove_stable() -> None:
    scene = {"entities": [{"id": "a", "tags": ["alpha", "beta"]}]}

    update_entity_field(scene, "a", "tags_add", ["beta", "gamma", "alpha", "delta"])
    assert scene["entities"][0]["tags"] == ["alpha", "beta", "gamma", "delta"]

    update_entity_field(scene, "a", "tags_remove", ["beta"])
    assert scene["entities"][0]["tags"] == ["alpha", "gamma", "delta"]
