import json
import pytest
import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch
from engine.tooling import assist_command

def test_mesh_assist_dry_run_diff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()
    
    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply:
        
        # Scenario: Triage produces a plan with create_scene and validate
        mock_triage.side_effect = lambda args: _mock_triage_diff(args, tmp_path)
        
        args = argparse.Namespace(world="worlds/diff.json", dry_run=True, diff=True)
        
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        exit_code = assist_command.run_assist_command(args)
        
        output = captured_out.getvalue()
        
        assert exit_code == 0
        assert "[ASSIST] Dry run" in output
        
        # Check for diff output
        assert "+++ scenes/new.json" in output
        assert '"name": "new"' in output
        assert '"version": 1' in output
        
        # Ensure no apply
        assert not mock_apply.called

def test_mesh_assist_diff_requires_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    args = argparse.Namespace(world="worlds/foo.json", dry_run=False, diff=True)
    
    from io import StringIO
    import sys
    captured_out = StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)
    
    exit_code = assist_command.run_assist_command(args)
    
    output = captured_out.getvalue()
    assert exit_code == 1
    assert "Error: --diff requires --dry-run" in output

def _mock_triage_diff(args, root):
    out_path = Path(args.out)
    plan = {
        "wizard": "fix-from-doctor",
        "version": 1,
        "actions": [
            {"type": "create_scene", "args": {"path": "scenes/new.json", "template": "empty"}, "description": "create"},
            {"type": "validate", "args": {"scene_path": "scenes/existing.json"}, "description": "validate"}
        ],
        "meta": {"unfixable": [], "touches": ["scenes/new.json"]}
    }
    out_path.write_text(json.dumps(plan))
    print(json.dumps({"plan_meta": {}, "warnings": []}))
    return 0
