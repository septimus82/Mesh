import json

from engine.tooling import pipeline_runner


def test_pipeline_preset_lint_json_deterministic(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "bad": {
                        "description": "invalid preset (banned pytest flag)",
                        "steps": [{"cmd": "python", "args": ["-m", "pytest", "--lf", "tests/test_anything.py"]}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result1 = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/test_world.json")
    out1 = capsys.readouterr().out

    result2 = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/test_world.json")
    out2 = capsys.readouterr().out

    assert result1.exit_code == 2
    assert result2.exit_code == 2
    assert out1 == out2

