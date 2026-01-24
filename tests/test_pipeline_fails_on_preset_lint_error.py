import json

from engine.tooling import pipeline_runner


def test_pipeline_fails_on_preset_lint_error(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "bad": {
                        "description": "invalid preset (banned pytest flag)",
                        "steps": [
                            {
                                "cmd": "python",
                                "args": ["-m", "pytest", "--lf", "tests/test_anything.py"],
                            }
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    def should_not_run(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("pipeline should fail before apply-plan")

    monkeypatch.setattr("engine.tooling.pipeline_runner.apply_plan", should_not_run)

    result = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/test_world.json")
    assert result.exit_code == 2

    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["stage"] == "preset_lint"
    assert payload["ok"] is False
    assert payload["version"] == 1
    assert "policy" in payload
    assert "presets_checked" in payload
    assert payload["presets_checked"] == 1
    assert payload["issues"]
    for issue in payload["issues"]:
        assert isinstance(issue, dict)
        assert set(["id", "preset", "step_index", "message"]).issubset(set(issue.keys()))
        assert issue["id"] == "preset_step_invalid"
