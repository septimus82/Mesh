import json
from pathlib import Path

import engine.paths
from engine.tooling.auto_wire import AutoWireController


def test_auto_wire_controller_writer_and_load_reset(tmp_path, monkeypatch):
    # Clear path cache to ensure we use tmp_path
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None

    monkeypatch.chdir(tmp_path)

    # Setup World and Scenes
    world_path = tmp_path / "worlds" / "test.json"
    world_path.parent.mkdir()

    hub_path = tmp_path / "scenes" / "region_hub.json"
    interior_path = tmp_path / "scenes" / "region_interior.json"
    hub_path.parent.mkdir(exist_ok=True)

    world_data = {
        "scenes": {
            "region_hub": {"path": str(hub_path)},
            "region_interior": {"path": str(interior_path)}
        }
    }
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")

    hub_data = {
        "name": "region_hub",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "hub"},
        "entities": []
    }
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")

    interior_data = {
        "name": "region_interior",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "interior"},
        "entities": []
    }
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")

    # --- Test 1: Writer Injection ---
    captured_writes = {}
    def capture_writer(path: Path, content: str):
        captured_writes[str(path)] = content

    def guarded_mkdir(self, *args, **kwargs):  # noqa: ARG001
        raise RuntimeError(f"Path.mkdir called in writer-injection mode: {self}")

    monkeypatch.setattr(Path, "mkdir", guarded_mkdir, raising=True)

    controller = AutoWireController(str(world_path), writer=capture_writer)
    controller.load()

    # Process should find missing links and trigger writes
    changes = controller.process(dry_run=False)

    assert len(changes) > 0
    assert len(captured_writes) > 0

    # Verify disk was NOT touched
    assert hub_path.read_text(encoding="utf-8") == json.dumps(hub_data, indent=2)
    assert interior_path.read_text(encoding="utf-8") == json.dumps(interior_data, indent=2)

    # Verify captured content has changes
    hub_captured = json.loads(captured_writes[str(hub_path)])
    assert "entities" in hub_captured
    # Should have SceneTransition
    has_transition = False
    for ent in hub_captured["entities"]:
        if "SceneTransition" in ent.get("behaviours", []):
            has_transition = True
            break
    assert has_transition, "Captured write should contain SceneTransition"

    # --- Test 2: Load Reset ---
    # Controller currently has modified scenes from the previous process() call
    assert len(controller.modified_scenes) > 0

    # Calling load() again should clear modified_scenes
    controller.load()

    assert len(controller.modified_scenes) == 0

    # Verify we can process again cleanly
    # Since we didn't write to disk, the files are still unwired.
    # So process() should find the same changes again.
    changes_2 = controller.process(dry_run=True)
    assert len(changes_2) == len(changes)
    # And modified_scenes should be populated again
    assert len(controller.modified_scenes) > 0
