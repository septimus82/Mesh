from engine.world_controller import WorldController


def test_world_controller_loads_scenes_and_links():
    data = {
        "id": "main",
        "start_scene": "village",
        "start_spawn": "gate",
        "scenes": {
            "village": {"path": "scenes/village.json", "label": "Village"},
            "forest": {"path": "scenes/forest.json", "label": "Forest"},
        },
        "links": [
            {"from": "village", "to": "forest", "via": "Door"},
            {"from": "forest", "to": "village", "via": "Trail"},
        ],
    }
    wc = WorldController(data)
    assert wc.id == "main"
    assert wc.get_scene_path("village") == "scenes/village.json"
    assert "forest" in wc.get_neighbors("village")
    meta = wc.export_metadata()
    assert meta["start_scene"] == "village"
    assert meta["start_spawn"] == "gate"


def test_find_scene_key_by_path():
    data = {
        "scenes": {
            "a": {"path": "scenes/a.json"},
        }
    }
    wc = WorldController(data)
    assert wc.find_scene_key_by_path("scenes/a.json") == "a"
