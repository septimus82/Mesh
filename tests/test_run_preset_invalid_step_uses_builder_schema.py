import argparse
import json
import subprocess
import sys
import types

import pytest

from engine.config import load_config
from engine.tooling import preset_commands


def test_run_preset_invalid_step_uses_builder_schema(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "bad": {
                        "description": "invalid preset (banned pytest flag)",
                        "steps": [{"cmd": "python", "args": ["-m", "pytest", "-k", "x"]}],
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()
    expected = preset_commands.build_preset_lint_stage_result(config)
    expected_line = json.dumps(expected, sort_keys=True) + "\n"
    assert expected["ok"] is False

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("preset steps must not execute when preset lint fails")

    monkeypatch.setattr(subprocess, "call", _unexpected)
    monkeypatch.setitem(sys.modules, "mesh_cli", types.SimpleNamespace(main=_unexpected))

    args = argparse.Namespace(name="bad")
    with pytest.raises(SystemExit) as excinfo:
        preset_commands.run_preset_command(args)

    assert excinfo.value.code == 2

    out = capsys.readouterr().out
    assert "[Mesh][Preset]" not in out
    assert out == expected_line
    payload = json.loads(out)
    assert payload == expected
    assert payload["stage"] == "preset_lint"

