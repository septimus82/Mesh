from __future__ import annotations

from pathlib import Path

from engine.tooling import schema_fix_ids
from engine.validators.schema_validation import validate_scene


def test_generate_entity_id_deterministic_and_collision_suffixing() -> None:
    used: set[str] = set()
    scene_slug = "door_field"

    ent = {"name": "Player", "x": 10.0, "y": 20.0}
    id1 = schema_fix_ids.generate_entity_id(scene_slug=scene_slug, entity=ent, used_ids=used)
    used.add(id1)

    # Same inputs => same base id, but collisions get suffixed.
    id2 = schema_fix_ids.generate_entity_id(scene_slug=scene_slug, entity=ent, used_ids=used)

    assert id1 != id2
    assert id2.startswith(id1 + "_")
    assert id2.endswith("_2")

    # Deterministic again: if used set is the same, we get the same suffix.
    used2 = {id1}
    id2b = schema_fix_ids.generate_entity_id(scene_slug=scene_slug, entity=ent, used_ids=used2)
    assert id2b == id2


def test_fix_then_validate_schema_strict_passes(tmp_path: Path) -> None:
    scene_path = tmp_path / "my scene.json"

    payload = {
        "name": "My Scene",
        "entities": [
            {
                "name": "Thing",
                "x": 1.0,
                "y": 2.0,
                "behaviours": ["TriggerZone"],
                "behaviour_config": {
                    "TriggerZone": {
                        "trigger_radius": 10,
                        "trigger_target": "foo",
                    }
                },
            }
        ],
    }

    updated, counts, changed = schema_fix_ids.fix_scene_payload(scene_path, payload)
    assert changed
    assert counts.ids_added == 1
    assert counts.zone_ids_added == 1

    errors = validate_scene(scene_path, updated, strict=True)
    assert errors == []
