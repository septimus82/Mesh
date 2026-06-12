import argparse
import json
from pathlib import Path
from unittest.mock import patch

from engine.tooling import assist_command


def test_mesh_assist_end_to_end(tmp_path, monkeypatch):
    # 1. Setup workspace
    monkeypatch.chdir(tmp_path)

    # Create config
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")

    # Create artifacts dir
    (tmp_path / "artifacts").mkdir()

    # Mock triage, apply, and test-ai to avoid running full stack
    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply, \
         patch("engine.tooling.plan_tester.run_test_ai") as mock_test:

        # Scenario 1: Triage produces actionable plan
        mock_triage.side_effect = lambda args: _mock_triage_success(args, tmp_path)
        mock_apply.return_value = 0
        mock_test.return_value = 0

        args = argparse.Namespace(world="worlds/broken.json", dry_run=False, diff=False)
        exit_code = assist_command.run_assist_command(args)

        assert exit_code == 0
        assert mock_triage.called
        assert mock_apply.called
        assert mock_test.called

        # Verify triage args
        triage_call_args = mock_triage.call_args[0][0]
        assert triage_call_args.world == "worlds/broken.json"
        assert triage_call_args.write_artifacts is True
        assert "assist_plan.json" in triage_call_args.out

def test_mesh_assist_no_actions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage:
        # Scenario 2: Triage produces empty plan
        mock_triage.side_effect = lambda args: _mock_triage_empty(args, tmp_path)

        args = argparse.Namespace(world="worlds/clean.json", dry_run=False, diff=False)
        exit_code = assist_command.run_assist_command(args)

        assert exit_code == 2 # Non-zero but specific code for "no actions"

def test_mesh_assist_refuse_mismatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply:

        # Scenario 3: Triage produces plan but output has warnings
        mock_triage.side_effect = lambda args: _mock_triage_mismatch(args, tmp_path)

        args = argparse.Namespace(world="worlds/mismatch.json", dry_run=False, diff=False)

        # Capture stdout to verify refusal message
        import sys
        from io import StringIO
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        exit_code = assist_command.run_assist_command(args)

        output = captured_out.getvalue()

        assert exit_code == 3
        lines = output.splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["version"] == 1
        assert payload["ok"] is False
        assert payload["stage"] == "triage_refuse"
        assert payload["reason"] == "action_hints_mismatch"
        assert payload["warnings"] == [
            {
                "id": "action_hints_mismatch",
                "message": "Plan action 'create_scene' on 'scenes/foo.json' has no corresponding action_hint.",
            }
        ]
        assert not mock_apply.called

def test_mesh_assist_refuse_plan_invalid_warning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply, \
         patch("engine.tooling.plan_tester.run_test_ai") as mock_test:

        mock_triage.side_effect = lambda args: _mock_triage_plan_invalid(args, tmp_path)

        args = argparse.Namespace(world="worlds/invalid.json", dry_run=False, diff=False)

        import sys
        from io import StringIO
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        exit_code = assist_command.run_assist_command(args)
        output = captured_out.getvalue()

        assert exit_code == 3
        lines = output.splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["version"] == 1
        assert payload["ok"] is False
        assert payload["stage"] == "triage_refuse"
        assert payload["reason"] == "plan_invalid"
        assert payload["warnings"] == [{"id": "plan_invalid_touches", "message": "Plan invalid: touches mismatch"}]

        assert not mock_apply.called
        assert not mock_test.called

def test_mesh_assist_legacy_string_warnings_still_refuse(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply:

        def legacy(args):
            out_path = Path(args.out)
            out_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "actions": [{"type": "create_scene", "args": {"path": "scenes/foo.json"}, "description": "fix"}],
                        "meta": {"touches": ["scenes/foo.json"]},
                    }
                )
            )
            print(json.dumps({"plan_meta": {}, "warnings": ["plan_invalid: touches mismatch"]}))
            return 0

        mock_triage.side_effect = legacy

        args = argparse.Namespace(world="worlds/legacy.json", dry_run=False, diff=False)

        import sys
        from io import StringIO
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        exit_code = assist_command.run_assist_command(args)
        output = captured_out.getvalue()

        assert exit_code == 3
        lines = output.splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["stage"] == "triage_refuse"
        assert payload["reason"] == "plan_invalid"
        assert any(w["id"] == "plan_invalid_touches" for w in payload["warnings"])
        assert not mock_apply.called

def test_mesh_assist_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts").mkdir()

    with patch("engine.tooling.triage_command.run_triage_command") as mock_triage, \
         patch("engine.tooling.plan_apply.apply_plan") as mock_apply:

        # Scenario 4: Dry run
        mock_triage.side_effect = lambda args: _mock_triage_success(args, tmp_path)

        args = argparse.Namespace(world="worlds/dry.json", dry_run=True, diff=False)

        import sys
        from io import StringIO
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)

        exit_code = assist_command.run_assist_command(args)

        output = captured_out.getvalue()

        assert exit_code == 0
        assert "[ASSIST] Dry run" in output
        assert "[ASSIST] Actions: 1" in output
        assert not mock_apply.called

def _mock_triage_success(args, root):
    # Write a plan with actions
    out_path = Path(args.out)
    plan = {
        "wizard": "fix-from-doctor",
        "version": 1,
        "actions": [{"type": "create_scene", "args": {"path": "scenes/foo.json"}, "description": "fix"}],
        "meta": {"unfixable": [], "touches": ["scenes/foo.json"]}
    }
    out_path.write_text(json.dumps(plan))
    # Print clean JSON
    print(json.dumps({"plan_meta": {}, "warnings": []}))
    return 0

def _mock_triage_empty(args, root):
    # Write a plan with no actions
    out_path = Path(args.out)
    plan = {
        "wizard": "fix-from-doctor",
        "version": 1,
        "actions": [],
        "meta": {"unfixable": []}
    }
    out_path.write_text(json.dumps(plan))
    print(json.dumps({"plan_meta": {}, "warnings": []}))
    return 0

def _mock_triage_mismatch(args, root):
    # Write a plan with actions
    out_path = Path(args.out)
    plan = {
        "wizard": "fix-from-doctor",
        "version": 1,
        "actions": [{"type": "create_scene", "args": {"path": "scenes/foo.json"}, "description": "fix"}],
        "meta": {"unfixable": []}
    }
    out_path.write_text(json.dumps(plan))
    # Print JSON with warnings
    print(
        json.dumps(
            {
                "plan_meta": {},
                "warnings": [
                    {
                        "id": "action_hints_mismatch",
                        "message": "Plan action 'create_scene' on 'scenes/foo.json' has no corresponding action_hint.",
                    }
                ],
            }
        )
    )
    return 0

def _mock_triage_plan_invalid(args, root):
    out_path = Path(args.out)
    plan = {
        "wizard": "fix-from-doctor",
        "version": 1,
        "actions": [{"type": "create_scene", "args": {"path": "scenes/foo.json"}, "description": "fix"}],
        "meta": {"unfixable": [], "touches": []}
    }
    out_path.write_text(json.dumps(plan))
    print(json.dumps({"plan_meta": {}, "warnings": [{"id": "plan_invalid_touches", "message": "Plan invalid: touches mismatch"}]}))
    return 0
