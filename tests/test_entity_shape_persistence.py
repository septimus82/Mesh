from __future__ import annotations

import pytest

from engine.geometry_tools import sanitize_poly
from engine.scene_loader import SceneLoader
from engine.scene_serializer import compact_scene_payload

pytestmark = pytest.mark.builtin_behaviours

def _normalize(points: list[list[float]] | list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in points]


def test_entity_shape_persistence_round_trip() -> None:
    loader = SceneLoader()
    scene = {
        "entities": [
            {
                "name": "shape_entity",
                "x": 10,
                "y": 20,
                "collision_poly": [[0, 0], [8, 0], [0, 8]],
                "occluder_poly": [[-4, -4], [4, -4], [4, 4], [-4, 4]],
            },
            {
                "name": "degenerate_entity",
                "x": 0,
                "y": 0,
                "collision_poly": [[0, 0], [0, 0]],
            },
        ]
    }

    full = loader.apply_scene_defaults(scene)
    compact = compact_scene_payload(full)
    restored = loader.apply_scene_defaults(compact)
    restored["entities"] = [loader.apply_entity_defaults(e) for e in restored["entities"]]

    entity = restored["entities"][0]
    assert _normalize(entity["collision_poly"]) == _normalize(scene["entities"][0]["collision_poly"])
    assert _normalize(entity["occluder_poly"]) == _normalize(scene["entities"][0]["occluder_poly"])

    degenerate = restored["entities"][1]
    assert sanitize_poly(degenerate["collision_poly"]) == []
