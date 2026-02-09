from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine import runtime_settings
from engine.editor.editor_focus_model import FOCUS_PROJECT_EXPLORER
from engine.editor_commands import filter_commands, get_all_commands, run_command
from engine.editor_runtime import input as editor_input
from tests._session_stub import make_session_stub


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
        self._palette_open = False
        self.search = self._SearchState()
        self.window = SimpleNamespace()
        self.panels = self._StubPanels(self)
        self.session = make_session_stub()

    class _SearchState:
        def __init__(self) -> None:
            self._query = "oops"
            self._index = 3

        @property
        def command_palette_query(self) -> str:
            return self._query

        @command_palette_query.setter
        def command_palette_query(self, value: str) -> None:
            self._query = str(value or "")

        @property
        def command_palette_index(self) -> int:
            return self._index

        @command_palette_index.setter
        def command_palette_index(self, value: int) -> None:
            self._index = int(value or 0)

        def clear_command_palette_state(self) -> None:
            self._query = ""
            self._index = 0

        def get_command_palette_state(self) -> tuple[str, int]:
            return (self._query, int(self._index))

        def backspace_command_palette(self) -> bool:
            if not self._query:
                return False
            self._query = self._query[:-1]
            self._index = 0
            return True

        def move_command_palette_selection(self, delta: int) -> None:
            self._index = max(0, int(self._index) + int(delta))

        def is_search_focused(self) -> bool:
            return False

        def focus_search_for_active_panel(self) -> bool:
            return False

    class _StubPanels:
        def __init__(self, controller: "_StubPaletteController") -> None:
            self._controller = controller

        def is_command_palette_open(self) -> bool:
            return bool(self._controller._palette_open)

        def toggle_command_palette(self) -> bool:
            self._controller._palette_open = not self._controller._palette_open
            return self._controller._palette_open

        def close_command_palette(self) -> None:
            self._controller._palette_open = False

        def dispatch_input(self, _key: int, _modifiers: int) -> bool:
            return False

    def run_editor_action(self, action_id: str) -> bool:
        if action_id == "editor.command_palette.toggle":
            opened = self.panels.toggle_command_palette()
            if opened:
                self.search.command_palette_query = ""
                self.search.command_palette_index = 0
            return True
        if action_id == "editor.command_palette.close":
            self.panels.close_command_palette()
            self.search.command_palette_query = ""
            self.search.command_palette_index = 0
            return True
        return False


@pytest.mark.fast
def test_command_palette_filter_order() -> None:
    commands = get_all_commands(None)
    filtered = filter_commands(commands, "preset")
    titles = [cmd.title for cmd in filtered[:8]]
    # HD-2D presets come first (sorted by filter score), then lighting presets
    assert titles == [
        "HD-2D Preset: Noir",
        "HD-2D Preset: Soft",
        "HD-2D Preset: Crisp",
        "HD-2D Preset: Dreamy",
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
    assert controller._palette_open is True
    assert controller.search.command_palette_query == ""
    assert controller.search.command_palette_index == 0

    closed = editor_input.handle_input(controller, optional_arcade.arcade.key.ESCAPE, 0)
    assert closed is True
    assert controller._palette_open is False


@pytest.mark.fast
def test_command_palette_project_explorer_focus_boosts_results() -> None:
    commands = get_all_commands(None)
    filtered = filter_commands(commands, "copy path", focus_target=FOCUS_PROJECT_EXPLORER)
    assert filtered[0].id == "editor.project_explorer.copy_path"

    filtered2 = filter_commands(commands, "select all", focus_target=FOCUS_PROJECT_EXPLORER)
    assert filtered2[0].id == "editor.project_explorer.select_all"
