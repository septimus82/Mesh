import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
from engine.tooling import assist_command
import engine.paths

def test_mesh_assist_dry_run_summary_json(tmp_path, monkeypatch):
    """Verify dry-run summary JSON output."""
    
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
    identical_data = {
        "name": "Identical",
        "version": 1,
        "schema_version": 1
    }
    identical_file.write_text(json.dumps(identical_data, indent=2, sort_keys=False), encoding="utf-8")
    
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
                "type": "polish_scene",
                "args": {"path": str(identical_file), "compact_only": True},
                "description": "Polish Identical"
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
    
    # Mock triage command to just return success
    with patch("engine.tooling.triage_command.run_triage_command", return_value=0):
        
        # Run command with --dry-run and --summary-json
        args = SimpleNamespace()
        args.world = "test_world"
        args.dry_run = True
        args.diff = False
        args.summary_json = True
        
        # Capture stdout
        from io import StringIO
        import sys
        
        captured_out = StringIO()
        with patch("sys.stdout", captured_out):
            exit_code = assist_command.run_assist_command(args)
            
        output = captured_out.getvalue()
        
        assert exit_code == 0
        
        # Parse JSON
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON:\n{output}")
            
        # Verify schema
        assert data["version"] == 1
        assert data["world"] == "test_world"
        assert data["actions"] == 3
        assert data["touches_ok"] is True
        
        # Verify would_write
        writes = data["would_write"]
        assert len(writes) == 2
        
        # Check sorting and content
        # Paths should be normalized
        new_path = str(tmp_path / "new.json").replace("\\", "/")
        existing_path = str(existing_file).replace("\\", "/")
        
        # Sort order depends on path string
        expected_writes = sorted([
            {"path": existing_path, "kind": "~changed"},
            {"path": new_path, "kind": "+added"}
        ], key=lambda x: x["path"])
        
        assert writes == expected_writes

        assert data["touches"] == sorted(data["touches"])
        assert data["captured_writes"] == sorted(data["captured_writes"])
        assert set(data["captured_writes"]).issubset(set(data["touches"]))
        
        # Verify skipped_identical
        assert data["skipped_identical"] == 1
        
        # Verify next
        assert "mesh apply-plan --from-triage" in data["next"]
        
        # Verify no extra text (strict JSON check was done by json.loads, but let's ensure no leading/trailing garbage if possible)
        # json.loads ignores whitespace, but if there was text before '{', it would fail.
        # If there was text after '}', it might fail depending on how we parse.
        # But we captured stdout, so `output` is the whole thing.
        assert output.strip().startswith("{")
        assert output.strip().endswith("}")

def test_mesh_assist_summary_json_requires_dry_run(tmp_path, monkeypatch):
    """Verify --summary-json requires --dry-run."""
    
    args = SimpleNamespace()
    args.world = "test_world"
    args.dry_run = False
    args.diff = False
    args.summary_json = True
    
    # Capture stdout
    from io import StringIO
    import sys
    
    captured_out = StringIO()
    with patch("sys.stdout", captured_out):
        exit_code = assist_command.run_assist_command(args)
        
    output = captured_out.getvalue()
    
    assert exit_code == 1
    assert "Error: --summary-json requires --dry-run" in output
