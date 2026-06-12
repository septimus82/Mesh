import argparse
import json
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import mesh_cli
from engine.tooling import assist_command, pipeline_runner


def test_next_hints_start_with_preset_lint_in_assist_summary_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    plan_path = tmp_path / "artifacts" / "assist_plan.json"
    plan_path.parent.mkdir(parents=True)

    plan_data = {"wizard": "fix-from-doctor", "version": 1, "actions": [], "inputs": {"meta": {"touches": []}}}
    plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

    with patch("engine.tooling.triage_command.run_triage_command", return_value=0):
        args = SimpleNamespace(world="test_world", dry_run=True, diff=False, summary_json=True, also_text=False)
        out = StringIO()
        with patch("sys.stdout", out):
            rc = assist_command.run_assist_command(args)

    assert rc == 0
    payload = json.loads(out.getvalue())
    assert payload["next"][0] == "mesh preset lint"


def test_next_hints_start_with_preset_lint_in_pipeline_output(capsys):
    with patch("engine.tooling.pipeline_runner.apply_plan", side_effect=SystemExit(1)):
        result = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/test_world.json")

    assert result.exit_code == 1
    lines = capsys.readouterr().out.splitlines()
    idx = lines.index("[PIPELINE] Next:")
    assert lines[idx + 1] == "  mesh preset lint"


def test_next_hints_start_with_preset_lint_in_apply_plan_from_triage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        command="apply-plan",
        from_triage=True,
        plan_path=None,
        no_lint=False,
        dry_run=False,
        run_tests=False,
        ai_safe=False,
    )

    plan_path = Path("artifacts/triage_last_plan.json")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({"wizard": "fix-from-doctor", "version": 1, "inputs": {"meta": {"touches": []}}, "actions": []}), encoding="utf-8")

    with (
        patch("mesh_cli.ai.PlanExecutor") as MockExecutor,
        patch("mesh_cli.ai.plan_linter") as mock_linter,
        patch("engine.tooling.plan_tester.PlanTester") as MockTester,
    ):
        mock_executor_instance = MockExecutor.return_value
        mock_executor_instance.execute.return_value = True
        mock_executor_instance.summary = {}

        mock_linter.lint_ai_plan.return_value = []
        mock_linter.lint_plan.return_value = []
        MockTester.return_value.run_ai_tests.return_value.passed = True

        out = StringIO()
        monkeypatch.setattr(sys, "stdout", out)

        rc = mesh_cli._handle_apply_plan(args)
        assert rc == 0

    lines = out.getvalue().splitlines()
    idx = lines.index("Next commands:")
    assert lines[idx + 1] == "  mesh preset lint"
