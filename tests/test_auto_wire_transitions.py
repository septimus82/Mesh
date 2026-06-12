import json

import pytest

from engine.tooling.auto_wire import AutoWireController


@pytest.fixture
def mock_world(tmp_path):
    world_file = tmp_path / "world.json"
    scene_a = tmp_path / "scene_a.json"
    scene_b = tmp_path / "scene_b.json"

    world_data = {
        "scenes": {
            "scene_a": {"path": str(scene_a)},
            "scene_b": {"path": str(scene_b)}
        }
    }

    scene_a_data = {
        "layers": {
            "entities": {
                "entities": {
                    "1": {
                        "behaviours": {
                            "SceneTransition": {
                                "target_scene": "scene_b.json"
                            }
                        }
                    }
                }
            }
        }
    }

    scene_b_data = {
        "layers": {}
    }

    world_file.write_text(json.dumps(world_data))
    scene_a.write_text(json.dumps(scene_a_data))
    scene_b.write_text(json.dumps(scene_b_data))

    return world_file

def test_auto_wire_detects_missing_backlink(mock_world):
    controller = AutoWireController(str(mock_world))
    controller.load()

    changes = controller.process(dry_run=True)

    assert len(changes) == 1
    assert "Added transition from scene_b to scene_a" in changes[0]

def test_auto_wire_applies_changes(mock_world):
    controller = AutoWireController(str(mock_world))
    controller.load()

    controller.process(dry_run=False)

    # Reload scene_b to check for new entity
    scene_b_path = mock_world.parent / "scene_b.json"
    with open(scene_b_path) as f:
        data = json.load(f)

    entities = data["layers"]["entities"]["entities"]
    assert len(entities) == 1
    entity = list(entities.values())[0]
    assert "SceneTransition" in entity["behaviours"]
    assert entity["behaviour_config"]["SceneTransition"]["target_scene"].endswith("scene_a.json")
    assert "auto_wired" in entity["tags"]

def test_auto_wire_hub_interior_heuristic(tmp_path):
    world_file = tmp_path / "world.json"
    hub = tmp_path / "Test_hub.json"
    interior = tmp_path / "Test_interior.json"

    world_data = {
        "scenes": {
            "Test_hub": {"path": str(hub)},
            "Test_interior": {"path": str(interior)}
        }
    }

    hub.write_text(json.dumps({"layers": {}}))
    interior.write_text(json.dumps({"layers": {}}))
    world_file.write_text(json.dumps(world_data))

    controller = AutoWireController(str(world_file))
    controller.load()
    changes = controller.process(dry_run=True)

    assert len(changes) == 2
    assert any("Test_hub to Test_interior" in c for c in changes)
    assert any("Test_interior to Test_hub" in c for c in changes)
