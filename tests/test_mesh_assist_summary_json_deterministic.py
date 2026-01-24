import pytest
import json
import argparse
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.tooling import assist_command

def test_mesh_assist_summary_json_deterministic(tmp_path, capsys, monkeypatch):
    """
    Ensure assist --summary-json output is byte-for-byte deterministic.
    """
    monkeypatch.chdir(tmp_path)
    
    # Setup minimal broken world
    world_path = tmp_path / "world.json"
    world_path.write_text(json.dumps({"scenes": {"missing": {"path": "missing.json"}}}, indent=2))
    
    # Mock Triage to return a stable plan
    # We need to mock run_triage_command to write a plan and return 0
    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage:
        def side_effect(args):
            # Write a fake plan
            plan_path = Path(args.out)
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_data = {
                "version": 1,
                "meta": {"touches": ["missing.json"], "unfixable": []},
                "actions": [
                    {
                        "type": "create_scene",
                        "args": {"path": "missing.json", "template": "empty"},
                        "description": "Create missing scene"
                    }
                ]
            }
            plan_path.write_text(json.dumps(plan_data, indent=2), encoding="utf-8")
            
            # Print fake triage output
            print(json.dumps({
                "version": 1,
                "warnings": [],
                "plan_meta": plan_data["meta"]
            }))
            return 0
            
        mock_triage.side_effect = side_effect
        
        # Run 1
        args = argparse.Namespace(
            world="world.json",
            dry_run=True,
            summary_json=True,
            diff=False,
            also_text=False
        )
        
        # We need to clear capsys before run
        capsys.readouterr()
        
        assist_command.run_assist_command(args)
        out1 = capsys.readouterr().out
        
        # Run 2
        assist_command.run_assist_command(args)
        out2 = capsys.readouterr().out
        
        # Assert Determinism
        assert out1 == out2, "Assist summary JSON not deterministic"
        
        # Parse JSON
        try:
            data = json.loads(out1)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {out1}")
            
        assert "version" in data
        assert data["version"] == 1
        assert "would_write" in data
        assert "next" in data
        assert "actions" in data
        assert data["actions"] == 1
        
        # Check would_write sorted
        paths = [item["path"] for item in data["would_write"]]
        assert paths == sorted(paths), "would_write paths not sorted"
        
        # Check paths use forward slashes
        for p in paths:
            assert "\\" not in p, f"Path contains backslash: {p}"
