from __future__ import annotations


def test_entity_paint_add_remove_is_idempotent() -> None:
    from engine.entity_paint_mode import apply_add_entity, apply_remove_entity

    scene = {"entities": []}
    changed, entity_id = apply_add_entity(scene, scene_path="scenes/foo.json", prefab_id="slime_blob", x=10.0, y=20.0)
    assert changed is True
    assert len(scene["entities"]) == 1

    changed2, entity_id2 = apply_add_entity(scene, scene_path="scenes/foo.json", prefab_id="slime_blob", x=10.0, y=20.0)
    assert changed2 is False
    assert entity_id2 == entity_id
    assert len(scene["entities"]) == 1

    assert apply_remove_entity(scene, entity_id=entity_id) is True
    assert len(scene["entities"]) == 0


def test_entity_paint_remove_does_not_delete_player() -> None:
    from engine.entity_paint_mode import apply_remove_entity

    scene = {
        "entities": [
            {"id": "p", "prefab_id": "player", "tag": "player", "x": 0.0, "y": 0.0},
        ]
    }
    assert apply_remove_entity(scene, entity_id="p") is False
    assert len(scene["entities"]) == 1

