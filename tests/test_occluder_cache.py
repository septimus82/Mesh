from __future__ import annotations

from engine.lighting import occluders


def test_entity_occluder_cache_reuses_world_points(monkeypatch) -> None:
    occluders.reset_entity_occluder_cache()
    calls: list[tuple] = []

    def _convert(points, base_x, base_y):  # noqa: ANN001
        calls.append((tuple(points), float(base_x), float(base_y)))
        return [(base_x + p[0], base_y + p[1]) for p in points]

    monkeypatch.setattr(occluders, "_convert_poly_to_world", _convert)

    scene = {
        "entities": [
            {
                "id": "e1",
                "x": 5,
                "y": 6,
                "occluder_poly": [[0, 0], [2, 0], [0, 2]],
            }
        ]
    }

    first = occluders.build_entity_occluders_from_scene_payload(scene)
    second = occluders.build_entity_occluders_from_scene_payload(scene)

    assert first == second
    assert len(calls) == 1

    scene["entities"][0]["x"] = 6
    _ = occluders.build_entity_occluders_from_scene_payload(scene)
    assert len(calls) == 2
