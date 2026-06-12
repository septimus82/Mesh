import pytest

from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

def test_apply_scene_defaults():
    loader = SceneLoader()
    raw = {"name": "Test Scene"}
    processed = loader.apply_scene_defaults(raw)

    assert processed["name"] == "Test Scene"
    assert processed["version"] == 1
    assert "settings" in processed
    assert "layers" in processed
    assert "entities" in processed
    assert processed["settings"]["background_color"] == "dark_blue_gray"

def test_validate_scene_valid():
    loader = SceneLoader()
    scene = {
        "name": "Valid Scene",
        "entities": [
            {
                "sprite": "assets/test.png",
                "x": 100,
                "y": 100
            }
        ]
    }
    # We need to apply defaults first because validate_scene expects them
    scene = loader.apply_scene_defaults(scene)
    report = loader.validate_scene(scene)
    assert report.ok
    assert not report.errors

def test_validate_scene_invalid_entity():
    loader = SceneLoader()
    scene = {
        "name": "Invalid Scene",
        "entities": [
            {
                "sprite": "assets/test.png",
                # Missing x and y
            }
        ]
    }
    scene = loader.apply_scene_defaults(scene)
    report = loader.validate_scene(scene)
    assert not report.ok
    assert any("missing required field 'x'" in err for err in report.errors)

def test_validate_scene_invalid_structure():
    loader = SceneLoader()
    # Scene must be a dict
    report = loader.validate_scene([])
    assert not report.ok
    assert "Scene root must be a JSON object" in report.errors[0]
