from __future__ import annotations


def test_command_palette_recent_scene_disabled_reason() -> None:
    from engine.command_palette import build_default_commands

    class _Window:
        @staticmethod
        def get_recent_scenes() -> list[str]:
            return []

    window = _Window()
    cmd = next(c for c in build_default_commands(window) if c.id == "scene.recent")
    enabled, reason = cmd.is_enabled(window)
    assert enabled is False
    assert reason == "empty"

