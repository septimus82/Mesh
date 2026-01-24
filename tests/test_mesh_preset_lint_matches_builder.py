import argparse
import json

from engine.config import load_config
from engine.tooling import preset_commands


def test_mesh_preset_lint_matches_builder_and_is_deterministic(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "with-env": {
                        "description": "valid preset with env",
                        "env": {"GOOD": "ok"},
                        "steps": [
                            {
                                "cmd": "python",
                                "args": ["-m", "pytest", "-q", "tests/test_agent_rules_doc_guard.py"],
                            }
                        ],
                    },
                    "no-env": {
                        "description": "valid preset",
                        "steps": [
                            {
                                "cmd": "python",
                                "args": ["-m", "pytest", "-q", "tests/test_agent_rules_doc_guard.py"],
                            }
                        ],
                    },
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()
    expected = preset_commands.build_preset_lint_stage_result(config)

    args = argparse.Namespace()
    ret1 = preset_commands.run_preset_lint_command(args)
    out1 = capsys.readouterr().out

    assert ret1 == (0 if expected["ok"] else 2)
    parsed1 = json.loads(out1.strip())
    assert parsed1 == expected

    ret2 = preset_commands.run_preset_lint_command(args)
    out2 = capsys.readouterr().out
    assert ret2 == (0 if expected["ok"] else 2)
    assert out1 == out2

