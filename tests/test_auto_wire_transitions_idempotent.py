import json
from pathlib import Path

import engine.paths
from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Plan


def test_auto_wire_transitions_idempotent(tmp_path, monkeypatch):
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

    plan_dict = {
        "actions": [
            {
                "type": "auto_wire_transitions",
                "args": {
                    "world_path": str(world_path)
                },
                "description": "Auto Wire"
            }
        ],
        "inputs": {
            "meta": {
                "touches": [
                    str(hub_path).replace("\\", "/"),
                    str(interior_path).replace("\\", "/"),
                    str(world_path).replace("\\", "/")
                ]
            }
        }
    }
    plan = Plan.from_dict(plan_dict)

    # 1. First Run (Real Execution)
    executor = PlanExecutor(dry_run=False)
    executor.execute(plan, ai_safe=True)

    # Verify transitions added
    hub_content_1 = hub_path.read_text(encoding="utf-8")
    interior_content_1 = interior_path.read_text(encoding="utf-8")

    assert "SceneTransition" in hub_content_1
    assert "SceneTransition" in interior_content_1
    assert "region_interior.json" in hub_content_1.replace("\\", "/")
    assert "region_hub.json" in interior_content_1.replace("\\", "/")

    # Count transitions
    assert hub_content_1.count("SceneTransition") == 2 # One in behaviours list, one in config key
    assert interior_content_1.count("SceneTransition") == 2

    # 2. Second Run (Idempotency Check)
    executor.execute(plan, ai_safe=True)

    hub_content_2 = hub_path.read_text(encoding="utf-8")
    interior_content_2 = interior_path.read_text(encoding="utf-8")

    assert hub_content_2 == hub_content_1
    assert interior_content_2 == interior_content_1

    # 3. Writer Capture Idempotency
    captured_1 = {}
    def capture_1(path: Path, content: str):
        captured_1[str(path)] = content

    executor_capture_1 = PlanExecutor(dry_run=False, writer=capture_1)
    # We need to reset the files to original state or use a new temp dir?
    # Actually, the requirement says "writer-capture mode (assist dry-run diff path)".
    # If we run it on the ALREADY WIRED files, it should produce NO writes (or identical writes if it rewrites same content).
    # Ideally it should produce NO writes if it's truly idempotent and detects existing links.
    # But if it rewrites the file with same content, that's also technically idempotent but less efficient.
    # Let's see what AutoWireController does. It only calls _save_changes if there are changes.

    executor_capture_1.execute(plan, ai_safe=True)

    # Since files are already wired, we expect NO changes.
    assert len(captured_1) == 0

    # Now let's test the case where we start from scratch and capture twice.
    # Reset files
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")

    captured_run_1 = {}
    def capture_run_1(path: Path, content: str):
        captured_run_1[str(path)] = content

    executor_run_1 = PlanExecutor(dry_run=False, writer=capture_run_1)
    executor_run_1.execute(plan, ai_safe=True)

    assert len(captured_run_1) == 2

    captured_run_2 = {}
    def capture_run_2(path: Path, content: str):
        captured_run_2[str(path)] = content

    executor_run_2 = PlanExecutor(dry_run=False, writer=capture_run_2)
    executor_run_2.execute(plan, ai_safe=True)

    # Verify outputs are identical
    assert captured_run_1.keys() == captured_run_2.keys()
    for k in captured_run_1:
        assert captured_run_1[k] == captured_run_2[k]
