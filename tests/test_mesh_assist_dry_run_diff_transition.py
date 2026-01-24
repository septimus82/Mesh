import json
import pytest
import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch
from engine.tooling import assist_command

def test_mesh_assist_dry_run_diff_transition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    
    # Create a dummy scene
    scene_path = tmp_path / "scenes" / "dummy.json"
    scene_path.parent.mkdir()
    scene_data = {
        "name": "dummy",
        "version": 1,
        "entities": []
    }
    scene_path.write_text(json.dumps(scene_data, indent=2), encoding="utf-8")
    
    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply:
        
        # Mock triage to return a plan with add_transition
        def _mock_triage(args, root):
            plan = {
                "actions": [
                    {
                        "type": "add_transition",
                        "args": {
                            "scene_path": str(scene_path),
                            "target_scene": "scenes/other.json",
                            "x": 10,
                            "y": 20
                        },
                        "description": "Add transition"
                    }
                ],
                "meta": {"touches": ["scenes/dummy.json"]},
            }
            (root / "artifacts" / "assist_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            return 0

        mock_triage.side_effect = lambda args: _mock_triage(args, tmp_path)
        
        args = argparse.Namespace(world="worlds/test.json", dry_run=True, diff=True)
        
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        exit_code = assist_command.run_assist_command(args)
        
        output = captured_out.getvalue()
        
        assert exit_code == 0
        
        # Check for diff output
        # Note: difflib output format depends on paths
        assert f"--- {scene_path}" in output
        assert f"+++ {scene_path}" in output
        assert '+      "name": "Transition",' in output
        assert '+      "tag": "trigger",' in output
        assert '+          "target_scene": "scenes/other.json",' in output
        
        # Ensure file on disk is UNCHANGED
        current_content = scene_path.read_text(encoding="utf-8")
        assert json.loads(current_content) == scene_data
        assert "Transition" not in current_content

def test_mesh_assist_dry_run_diff_transition_missing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    
    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage:
        
        def _mock_triage(args, root):
            plan = {
                "actions": [
                    {
                        "type": "add_transition",
                        "args": {
                            "scene_path": "scenes/missing.json",
                            "target_scene": "scenes/other.json"
                        },
                        "description": "Add transition"
                    }
                ]
            }
            (root / "artifacts" / "assist_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            return 0

        mock_triage.side_effect = lambda args: _mock_triage(args, tmp_path)
        
        args = argparse.Namespace(world="worlds/test.json", dry_run=True, diff=True)
        
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        assist_command.run_assist_command(args)
        
        output = captured_out.getvalue()
        
        assert "(skipped) add_transition scenes/missing.json (file not found)" in output
