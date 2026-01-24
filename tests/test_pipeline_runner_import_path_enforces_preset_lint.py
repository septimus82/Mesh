import json
from unittest.mock import MagicMock, patch

from engine.tooling import pipeline_runner


def test_pipeline_runner_import_path_enforces_preset_lint(capsys):
    bad_config = MagicMock()
    bad_config.presets = {
        "bad": {
            "description": "invalid preset (banned pytest flag)",
            "steps": [{"cmd": "python", "args": ["-m", "pytest", "--lf", "tests/test_anything.py"]}],
        }
    }

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("pipeline should fail before apply-plan")

    with (
        patch("engine.tooling.pipeline_runner.load_config", return_value=bad_config),
        patch("engine.tooling.pipeline_runner.apply_plan", side_effect=should_not_run),
    ):
        result = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/test_world.json")

    assert result.exit_code == 2

    out = capsys.readouterr().out
    assert "[PIPELINE] Next:" not in out
    lines = out.splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["stage"] == "preset_lint"
    assert payload["ok"] is False
    assert payload["version"] == 1
    assert "policy" in payload
    assert "presets_checked" in payload
    assert "issues" in payload

