import json
import pytest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from engine.tooling import assist_command
import engine.paths

def test_mesh_assist_dry_run_diff_truncation(tmp_path, monkeypatch):
    """Verify dry-run diff truncation using real PlanExecutor and large content."""
    
    # Clear path cache
    engine.paths._CONTENT_ROOTS = None
    engine.paths._CACHED_CONFIG = None
    
    monkeypatch.chdir(tmp_path)
    
    # --- Setup ---
    # Create a dummy plan
    plan_path = tmp_path / "artifacts" / "assist_plan.json"
    plan_path.parent.mkdir(parents=True)
    
    # Create a file that will be modified with a large diff
    # We use polish_scene to rewrite it.
    # To ensure a large diff, we write it with indent=4, and polish_scene will rewrite with indent=2.
    # We add many items to make it long.
    existing_file = tmp_path / "large_diff.json"
    
    large_items = [{"id": f"item_{i}", "name": f"Item {i}", "visible": True} for i in range(100)]
    scene_data = {
        "name": "Large Scene",
        "version": 1,
        "entities": large_items
    }
    
    # Write with indent=4
    existing_file.write_text(json.dumps(scene_data, indent=4), encoding="utf-8")
    
    plan_data = {
        "actions": [
            {
                "type": "polish_scene",
                "args": {"path": str(existing_file), "compact_only": True},
                "description": "Polish Large Scene"
            }
        ],
        "inputs": {
            "meta": {
                "touches": [
                    str(existing_file).replace("\\", "/")
                ]
            }
        }
    }
    plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
    
    # Mock triage command to just return success
    with patch("engine.tooling.triage_command.run_triage_command", return_value=0):
        
        # Run command with small limit
        args = SimpleNamespace()
        args.world = "test_world"
        args.dry_run = True
        args.diff = True
        args.summary_json = False
        args.also_text = False
        args.max_diff_lines = 10
        
        # Capture stdout
        from io import StringIO
        import sys
        
        captured_out = StringIO()
        with patch("sys.stdout", captured_out):
            exit_code = assist_command.run_assist_command(args)
            
        output = captured_out.getvalue()
        
        assert exit_code == 0
        
        # Verify truncation
        assert "[ASSIST] Diff truncated:" in output
        assert "(showing first 10 lines)" in output
        
        # Count lines in the diff block
        lines = output.splitlines()
        diff_start = -1
        diff_end = -1
        for i, line in enumerate(lines):
            if line.startswith("[ASSIST] Diff:"):
                diff_start = i + 1
            if line.startswith("[ASSIST] Diff truncated:"):
                diff_end = i
                break
        
        assert diff_start != -1
        assert diff_end != -1
        
        diff_lines = lines[diff_start:diff_end]
        assert len(diff_lines) == 10
        
        # Run command with large limit
        args.max_diff_lines = 2000
        
        captured_out = StringIO()
        with patch("sys.stdout", captured_out):
            exit_code = assist_command.run_assist_command(args)
            
        output = captured_out.getvalue()
        
        assert exit_code == 0
        assert "[ASSIST] Diff truncated:" not in output
        
        # Verify we see the whole diff
        # The file has 100 items, each taking multiple lines in JSON.
        # Even compacted, it's large.
        # indent=4 vs indent=2 means every line changes.
        # 100 items * ~5 lines/item = 500 lines.
        assert len(output.splitlines()) > 100
