from unittest.mock import patch

from engine.tooling import pipeline_runner


def test_pipeline_next_includes_preset_lint(capsys):
    # Mock apply_plan to raise SystemExit(1)
    with patch("engine.tooling.pipeline_runner.apply_plan", side_effect=SystemExit(1)):

        result = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/test_world.json")

        assert result.exit_code == 1

        out = capsys.readouterr().out

        lines = out.splitlines()
        assert "[PIPELINE] Next:" in lines
        idx = lines.index("[PIPELINE] Next:")
        assert lines[idx + 1] == "  mesh preset lint"
