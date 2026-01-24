import argparse
import json

import pytest

from engine.config import load_config
from engine.tooling import check, pipeline_runner, preset_commands


def test_preset_lint_output_equivalence_across_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "bad": {
                        "description": "invalid preset (banned pytest flag)",
                        "steps": [
                            {"cmd": "python", "args": ["-m", "pytest", "--lf", "tests/test_anything.py"]}
                        ],
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    config = load_config()
    expected = preset_commands.build_preset_lint_stage_result(config)
    expected_line = json.dumps(expected, sort_keys=True) + "\n"

    capsys.readouterr()
    ret = preset_commands.run_preset_lint_command(argparse.Namespace())
    assert ret == 2
    out = capsys.readouterr().out
    assert out.splitlines() == [expected_line.rstrip("\n")]
    assert json.loads(out) == expected
    assert out == expected_line

    capsys.readouterr()
    with pytest.raises(SystemExit) as excinfo:
        check.run_check(world_path="worlds/ignored.json")
    assert excinfo.value.code == 2
    out = capsys.readouterr().out
    assert out.splitlines() == [expected_line.rstrip("\n")]
    assert json.loads(out) == expected
    assert out == expected_line

    capsys.readouterr()
    result = pipeline_runner.run_pipeline_result(plan_path="plan.json", path="worlds/ignored.json")
    assert result.exit_code == 2
    out = capsys.readouterr().out
    assert out.splitlines() == [expected_line.rstrip("\n")]
    assert json.loads(out) == expected
    assert out == expected_line

