import json

from engine.config import load_config
from engine.tooling import preset_commands


def test_preset_lint_stage_schema_success_is_stable(tmp_path, monkeypatch):
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "presets": {
                    "good": {
                        "description": "valid preset",
                        "steps": [
                            {
                                "cmd": "python",
                                "args": ["-m", "pytest", "-q", "tests/test_agent_rules_doc_guard.py"],
                            }
                        ],
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    stage1 = preset_commands.build_preset_lint_stage_result(config)
    stage2 = preset_commands.build_preset_lint_stage_result(config)

    for stage in (stage1, stage2):
        assert set(["version", "ok", "stage", "policy", "issues", "presets_checked"]).issubset(stage.keys())
        assert stage["version"] == 1
        assert stage["stage"] == "preset_lint"
        assert stage["ok"] is True
        assert stage["issues"] == []
        assert stage["presets_checked"] == 1

    assert json.dumps(stage1, sort_keys=True) == json.dumps(stage2, sort_keys=True)

