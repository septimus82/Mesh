import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.tooling import assist_command
import engine.paths
from engine import json_io

def test_mesh_assist_dry_run_write_summary(tmp_path, monkeypatch):
    """Verify dry-run summary output."""
    
    # Clear path cache
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None
    
    monkeypatch.chdir(tmp_path)
    
    # --- Setup ---
    # Create a dummy plan
    plan_path = tmp_path / "artifacts" / "assist_plan.json"
    plan_path.parent.mkdir(parents=True)
    
    # Create a file that will be modified
    existing_file = tmp_path / "existing.json"
    existing_file.write_text('{"foo": "bar"}', encoding="utf-8")
    
    # Create a file that will be identical
    identical_file = tmp_path / "identical.json"
    json_io.write_json_atomic(identical_file, {"foo": "bar"})
    
    plan_data = {
        "actions": [
            {
                "type": "create_scene",
                "args": {"path": str(tmp_path / "new.json"), "template": "empty"},
                "description": "Create New"
            },
            {
                "type": "add_npc",
                "args": {"scene_path": str(existing_file), "name": "Guard", "x": 100, "y": 100},
                "description": "Modify Existing"
            },
            {
                "type": "add_npc",
                "args": {"scene_path": str(identical_file), "name": "Guard", "x": 100, "y": 100},
                "description": "Modify Identical (Simulated)" 
            }
        ],
        "inputs": {
            "meta": {
                "touches": [
                    str(tmp_path / "new.json").replace("\\", "/"),
                    str(existing_file).replace("\\", "/"),
                    str(identical_file).replace("\\", "/")
                ]
            }
        }
    }
    plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
    
    # Mock triage command to just return success (since we pre-seeded the plan)
    with patch("engine.tooling.triage_command.run_triage_command", return_value=0):
        
        # Mock PlanExecutor to simulate writes
        # We need to mock the executor used inside assist_command
        # But assist_command currently doesn't use PlanExecutor in dry-run (it just prints).
        # We will modify it to use PlanExecutor.
        
        # However, for the test to pass BEFORE we modify the code, we can't mock what isn't there.
        # So we will write the test assuming the new behavior.
        
        # We need to ensure that when PlanExecutor runs, it produces the expected "writes".
        # Since we are using the REAL PlanExecutor (with mocked writer), we need the actions to actually work.
        # create_scene works.
        # add_npc works (needs existing file).
        
        # For "identical", we need an action that writes the SAME content.
        # add_npc adds to the list, so it WILL change the file.
        # To simulate identical, we can use a custom action or just accept that
        # we can't easily simulate identical with standard actions unless we
        # pre-populate the file with the result.
        
        # Let's pre-populate identical_file with the result of add_npc
        # But add_npc appends.
        # If we want identical, we need the file to ALREADY have the NPC.
        # But add_npc might add it AGAIN (duplicate).
        # Unless add_npc checks for existence?
        # _add_npc implementation:
        # data.setdefault("entities", []).append(npc)
        # It appends blindly. So it will change.
        
        # Maybe use "create_quest"?
        # _create_quest checks: if not any(q["id"] == args["id"] ...): append
        # So if we pre-populate the quest, it won't append, but will it write?
        # _create_quest:
        # if not any(...):
        #    data...append(...)
        #    path.write_text(...)
        # So if it exists, it DOES NOT write.
        # That means capture_writer won't be called.
        # That's fine. If capture_writer isn't called, it won't be in the list.
        # But we want to test "if identical: don't list it".
        # This implies "if we write the SAME content, don't list it".
        # PlanExecutor._write_file calls writer(path, content).
        # If the action logic decides NOT to write, then we definitely don't list it.
        # But if the action logic writes the SAME content (e.g. overwrite with same data), we want to filter it out.
        
        # Let's use a mock action or just rely on `create_scene` with `force=True`?
        # `create_scene` checks existence.
        
        # Let's just use `add_npc` and accept it changes.
        # And for identical, let's manually invoke the writer with identical content in the test?
        # No, we are testing `assist_command`.
        
        # We can mock `PlanExecutor.execute` to populate `captured_writes` manually?
        # No, we want integration test.
        
        # Let's stick to:
        # 1. New file (create_scene) -> +added
        # 2. Modified file (add_npc) -> ~changed
        
        # To test identical filtering, we need an action that writes.
        # `polish_scene` writes back compacted data.
        # If the file is ALREADY compacted, it writes the same data.
        # Let's use `polish_scene`.
        
        # Setup identical file as already polished
        # compact_scene_payload removes empty settings and entities
        identical_data = {
            "name": "Identical",
            "version": 1,
            "schema_version": 1
        }
        # Compacted form (defaults removed)
        # polish_scene writes with stable formatting now.
        json_io.write_json_atomic(identical_file, identical_data)
        
        # Update plan to use polish_scene for identical
        plan_data["actions"][2] = {
            "type": "polish_scene",
            "args": {"path": str(identical_file), "compact_only": True},
            "description": "Polish Identical"
        }
        plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
        
        # Run command
        from types import SimpleNamespace
        args = SimpleNamespace()
        args.world = "test_world"
        args.dry_run = True
        args.diff = False
        args.summary_json = False
        
        # Capture stdout
        from io import StringIO
        import sys
        
        captured_out = StringIO()
        with patch("sys.stdout", captured_out):
            exit_code = assist_command.run_assist_command(args)
            
        output = captured_out.getvalue()
        
        assert exit_code == 0
        assert "[ASSIST] Dry run" in output
        assert f"[ASSIST] Actions: {len(plan_data['actions'])}" in output
        
        # Check for "Would write"
        assert "[ASSIST] Would write:" in output
        
        # Check for specific files
        # new.json -> +added
        assert f"[ASSIST] Write: {str(tmp_path / 'new.json')} (+added)" in output
        
        # existing.json -> ~changed
        assert f"[ASSIST] Write: {str(existing_file)} (~changed)" in output
        
        # identical.json -> SHOULD NOT BE LISTED
        assert str(identical_file) not in output


def test_mesh_assist_dry_run_write_summary_fails_on_touches_mismatch(tmp_path, monkeypatch):
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None

    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "worlds").mkdir()
    (tmp_path / "scenes").mkdir()

    world_path = tmp_path / "worlds" / "w.json"
    hub_path = tmp_path / "scenes" / "region_hub.json"
    interior_path = tmp_path / "scenes" / "region_interior.json"

    world_data = {
        "scenes": {
            "region_hub": {"path": "scenes/region_hub.json"},
            "region_interior": {"path": "scenes/region_interior.json"},
        }
    }
    world_path.write_text(json.dumps(world_data, indent=2), encoding="utf-8")

    hub_data = {
        "name": "region_hub",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "hub"},
        "entities": [
            {
                "name": "to_interior",
                "x": 0,
                "y": 0,
                "behaviours": ["SceneTransition"],
                "behaviour_config": {"SceneTransition": {"target_scene": "scenes/region_interior.json"}},
            }
        ],
    }
    hub_path.write_text(json.dumps(hub_data, indent=2), encoding="utf-8")

    interior_data = {
        "name": "region_interior",
        "version": 1,
        "settings": {"region_template": "hub-interior-dungeon", "scene_kind": "interior"},
        "entities": [],
    }
    interior_path.write_text(json.dumps(interior_data, indent=2), encoding="utf-8")

    plan_path = tmp_path / "artifacts" / "assist_plan.json"
    plan_data = {
        "version": 1,
        "meta": {"touches": ["worlds/w.json"]},
        "actions": [
            {
                "type": "auto_wire_transitions",
                "args": {"world_path": "worlds/w.json"},
                "description": "auto-wire",
            }
        ],
    }
    plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")

    with patch("engine.tooling.triage_command.run_triage_command", return_value=0):
        from types import SimpleNamespace
        args = SimpleNamespace()
        args.world = "worlds/w.json"
        args.dry_run = True
        args.diff = False
        args.summary_json = False

        from io import StringIO
        captured_out = StringIO()
        with patch("sys.stdout", captured_out):
            exit_code = assist_command.run_assist_command(args)

    assert exit_code == 3
    out = captured_out.getvalue()
    lines = out.splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["stage"] == "triage_refuse"
    assert payload["reason"] == "touches_mismatch"
    assert payload["ok"] is False
    assert "scenes/region_interior.json" in payload["missing"]
