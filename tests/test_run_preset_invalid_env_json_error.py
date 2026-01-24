import argparse
import json
import subprocess
import sys
import types

import pytest

from engine.config import load_config
from engine.tooling import preset_commands


def test_run_preset_invalid_env_json_error(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "bad-env": {
                        "description": "Bad env preset",
                        "env": {"bad": "ok"},
                        "steps": [
                            {"cmd": "python", "args": ["-m", "pytest", "tests/test_run_preset.py"]}
                        ],
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    expected = preset_commands.build_preset_lint_stage_result(load_config())
    expected_line = json.dumps(expected, sort_keys=True) + "\n"

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("preset steps must not execute when env is invalid")

    monkeypatch.setattr(subprocess, "call", _unexpected)
    monkeypatch.setitem(sys.modules, "mesh_cli", types.SimpleNamespace(main=_unexpected))

    args = argparse.Namespace(name="bad-env")
    with pytest.raises(SystemExit) as excinfo:
        preset_commands.run_preset_command(args)

    assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == expected_line
    payload = json.loads(captured.out)
    assert payload == expected
    assert payload["stage"] == "preset_lint"
    assert any(issue.get("id") == "preset_env_invalid" for issue in payload.get("issues", []))
