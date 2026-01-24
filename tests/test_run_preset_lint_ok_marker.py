import argparse
import json
from unittest.mock import MagicMock, patch

from engine.tooling import preset_commands


def test_run_preset_does_not_print_preset_lint_json_on_success(capsys):
    mock_config = MagicMock()
    mock_config.presets = {
        "ci_check": {
            "description": "CI check preset",
            "action": "release-check",
            "args": {"world_path": "worlds/main.json", "profile": "release"},
        }
    }
    mock_config.world_file = "worlds/main.json"

    ok_stage = {
        "version": 1,
        "ok": True,
        "stage": "preset_lint",
        "policy": {"version": 1},
        "issues": [],
        "presets_checked": 1,
    }

    with (
        patch("engine.tooling.preset_commands.load_config", return_value=mock_config),
        patch("engine.tooling.preset_commands.build_preset_lint_stage_result", return_value=ok_stage),
        patch("engine.tooling.release_command.release_check_command") as mock_release,
    ):
        preset_commands.run_preset_command(argparse.Namespace(name="ci_check"))

    out = capsys.readouterr().out
    assert '"stage": "preset_lint"' not in out
    assert json.dumps(ok_stage, sort_keys=True) not in out
    assert mock_release.called

