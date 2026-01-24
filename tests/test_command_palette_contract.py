from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine import runtime_settings
from engine.editor_commands import filter_commands, get_all_commands, run_command
from engine.editor_runtime import input as editor_input


class _StubEditorController:
    def __init__(self) -> None:
        self.lights_tool_active = False
        self.occluder_tool_active = False
        self.applied_presets: list[int] = []

    def toggle_lights_tool(self) -> None:
        self.lights_tool_active = not self.lights_tool_active

    def toggle_occluder_tool(self) -> None:
        self.occluder_tool_active = not self.occluder_tool_active

    def apply_lighting_preset_hotkey(self, index: int) -> None:
        self.applied_presets.append(int(index))


class _StubWindow:
    def __init__(self) -> None:
        self.editor_controller = _StubEditorController()
        self.engine_config = SimpleNamespace(
            music_volume=1.0,
            sfx_volume=1.0,
            fog_enabled=False,
            soft_shadows_enabled=False,
        )
        self.runtime_settings = runtime_settings.RuntimeSettings.from_config(self.engine_config)


class _StubPaletteController:
    def __init__(self) -> None:
        self.active = True
        self.command_palette_active = False
        self.command_palette_query = "oops"
        self.command_palette_index = 3
        self.window = SimpleNamespace()


@pytest.mark.fast
def test_command_palette_filter_order() -> None:
    commands = get_all_commands(None)
    filtered = filter_commands(commands, "preset")
    titles = [cmd.title for cmd in filtered[:4]]
    assert titles == [
        "Apply Lighting Preset 1",
        "Apply Lighting Preset 2",
        "Apply Lighting Preset 3",
        "Apply Lighting Preset 4",
    ]


@pytest.mark.fast
def test_command_palette_run_executes() -> None:
    window = _StubWindow()
    assert run_command("editor.light_tool.toggle", window) is True
    assert window.editor_controller.lights_tool_active is True
    assert run_command("editor.occluder_tool.toggle", window) is True
    assert window.editor_controller.occluder_tool_active is True

    assert run_command("editor.lighting_preset.2", window) is True
    assert window.editor_controller.applied_presets == [1]

    assert run_command("runtime.fog.toggle", window) is True
    assert window.runtime_settings.fog_enabled is True
    assert window.engine_config.fog_enabled is True

    assert run_command("runtime.soft_shadows.toggle", window) is True
    assert window.runtime_settings.soft_shadows_enabled is True
    assert window.engine_config.soft_shadows_enabled is True


@pytest.mark.fast
def test_command_palette_open_close() -> None:
    controller = _StubPaletteController()
    ctrl_mod = optional_arcade.arcade.key.MOD_CTRL

    opened = editor_input.handle_input(controller, optional_arcade.arcade.key.P, ctrl_mod)
    assert opened is True
    assert controller.command_palette_active is True
    assert controller.command_palette_query == ""
    assert controller.command_palette_index == 0

    closed = editor_input.handle_input(controller, optional_arcade.arcade.key.ESCAPE, 0)
    assert closed is True
    assert controller.command_palette_active is False
