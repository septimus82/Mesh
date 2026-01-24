from __future__ import annotations

from engine.lighting.occluders import build_entity_occluders_from_scene_payload


def test_occluder_poly_used_for_entity() -> None:
    scene = {
        "entities": [
            {
                "id": "e1",
                "x": 10,
                "y": 20,
                "occluder_poly": [[0, 0], [2, 0], [0, 2]],
            },
            {
                "id": "degenerate",
                "x": 0,
                "y": 0,
                "occluder_poly": [[0, 0], [0, 0]],
            },
        ]
    }

    occluders = build_entity_occluders_from_scene_payload(scene)
    assert len(occluders) == 1
    occ = occluders[0]
    assert occ["type"] == "poly"
    assert occ["points"] == [(10.0, 20.0), (12.0, 20.0), (10.0, 22.0)]
