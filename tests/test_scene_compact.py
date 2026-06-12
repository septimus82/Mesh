import pytest

from engine.scene_loader import DEFAULT_ENTITY, DEFAULT_LAYERS, DEFAULT_SETTINGS, SceneLoader
from engine.scene_serializer import compact_scene_payload

pytestmark = pytest.mark.builtin_behaviours

def test_compact_scene_removes_defaults():
    full_scene = {
        "settings": DEFAULT_SETTINGS.copy(),
        "layers": DEFAULT_LAYERS.copy(),
        "entities": [
            DEFAULT_ENTITY.copy()
        ]
    }
    # Add identity fields to entity so it's not empty
    full_scene["entities"][0]["name"] = "test_entity"
    full_scene["entities"][0]["x"] = 100
    full_scene["entities"][0]["y"] = 200

    compacted = compact_scene_payload(full_scene)

    assert "settings" not in compacted
    assert "layers" not in compacted
    assert len(compacted["entities"]) == 1
    entity = compacted["entities"][0]

    # Should only have identity fields
    assert entity["name"] == "test_entity"
    assert entity["x"] == 100
    assert entity["y"] == 200
    assert "sprite" not in entity # default
    assert "solid" not in entity # default

def test_compact_scene_preserves_non_defaults():
    scene = {
        "settings": {"music_volume": 0.5}, # non-default
        "entities": [
            {
                "name": "e1",
                "x": 0, "y": 0,
                "sprite": "assets/custom.png", # non-default
                "solid": True # non-default
            }
        ]
    }

    compacted = compact_scene_payload(scene)

    assert compacted["settings"]["music_volume"] == 0.5
    assert compacted["entities"][0]["sprite"] == "assets/custom.png"
    assert compacted["entities"][0]["solid"] is True

def test_compact_scene_round_trip():
    loader = SceneLoader()

    original = {
        "settings": {"music_volume": 0.5},
        "entities": [
            {
                "name": "e1",
                "x": 10, "y": 20,
                "sprite": "assets/custom.png",
                "behaviours": ["Patrol"]
            }
        ]
    }

    # 1. Apply defaults to get full state
    full = loader.apply_scene_defaults(original)

    # 2. Compact
    compacted = compact_scene_payload(full)

    # 3. Apply defaults again
    restored = loader.apply_scene_defaults(compacted)
    restored["entities"] = [loader.apply_entity_defaults(e) for e in restored["entities"]]

    # Compare core fields
    assert restored["settings"]["music_volume"] == 0.5
    assert restored["entities"][0]["sprite"] == "assets/custom.png"
    # Behaviours are normalized by apply_entity_defaults
    assert restored["entities"][0]["behaviours"][0]["type"] == "Patrol"

    # Check that defaults were restored
    assert restored["settings"]["background_color"] == DEFAULT_SETTINGS["background_color"]
    assert restored["entities"][0]["solid"] == DEFAULT_ENTITY["solid"]

def test_compact_behaviour_config():
    # Case 1: Empty config, no behaviours -> remove
    e1 = DEFAULT_ENTITY.copy()
    e1.update({"name": "e1", "x": 0, "y": 0, "behaviour_config": {}})

    c1 = compact_scene_payload({"entities": [e1]})
    assert "behaviour_config" not in c1["entities"][0]

    # Case 2: Config for unlisted behaviour -> remove
    e2 = DEFAULT_ENTITY.copy()
    e2.update({
        "name": "e2", "x": 0, "y": 0,
        "behaviours": [],
        "behaviour_config": {"Unused": {}}
    })
    c2 = compact_scene_payload({"entities": [e2]})
    assert "behaviour_config" not in c2["entities"][0]

    # Case 3: Config for listed behaviour -> keep
    e3 = DEFAULT_ENTITY.copy()
    e3.update({
        "name": "e3", "x": 0, "y": 0,
        "behaviours": ["Used"],
        "behaviour_config": {"Used": {}}
    })
    c3 = compact_scene_payload({"entities": [e3]})
    assert "behaviour_config" in c3["entities"][0]
    assert "Used" in c3["entities"][0]["behaviour_config"]

    # Case 4: Config with params -> keep
    e4 = DEFAULT_ENTITY.copy()
    e4.update({
        "name": "e4", "x": 0, "y": 0,
        "behaviours": [],
        "behaviour_config": {"UnusedButParams": {"p": 1}}
    })
    c4 = compact_scene_payload({"entities": [e4]})
    assert "behaviour_config" in c4["entities"][0]
    assert "UnusedButParams" in c4["entities"][0]["behaviour_config"]
