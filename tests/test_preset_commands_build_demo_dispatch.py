import argparse

from engine.tooling import preset_commands


def test_preset_build_demo_dispatch(monkeypatch) -> None:
    called: dict[str, bool] = {"ok": False}

    class _Config:
        presets = {
            "demo": {
                "description": "Demo preset",
                "action": "build-demo",
                "args": {"out": "dist/demo.zip"},
            }
        }

    monkeypatch.setattr(preset_commands, "load_config", lambda: _Config())
    monkeypatch.setattr(preset_commands, "build_preset_lint_stage_result", lambda _cfg: {"ok": True})

    def _handle_build_demo(_args: argparse.Namespace) -> int:
        called["ok"] = True
        return 0

    monkeypatch.setattr(preset_commands.build_demo_command, "handle_build_demo", _handle_build_demo)

    preset_commands.run_preset_command(argparse.Namespace(name="demo"))

    assert called["ok"] is True
