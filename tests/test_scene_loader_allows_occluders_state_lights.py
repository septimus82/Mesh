from __future__ import annotations

import pytest

from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

def test_scene_loader_allows_occluders_state_lights_without_unknown_key_warnings() -> None:
    loader = SceneLoader()
    scene = {
        "name": "Test Scene",
        "entities": [],
        "occluders": [{"id": "o1", "type": "rect", "x": 0, "y": 0, "width": 16, "height": 16}],
        "state": {"notes": "debug"},
        "lights": [{"id": "l1", "type": "point", "x": 0, "y": 0, "radius": 64}],
    }
    report = loader.validate_scene(scene, validate_entities=False)
    assert report.ok is True
    assert not any("Unknown top-level key" in warning for warning in report.warnings)

