from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor_commands import Command, filter_commands, get_all_commands
from engine.ui import format_command_palette_overlay_lines
from engine.ui_overlays.providers import editor_command_palette_provider

pytestmark = pytest.mark.fast


def _noop(_window: object) -> None:
    return None


def _command(
    command_id: str = "editor.example",
    title: str = "Example",
    shortcut: str | None = None,
) -> Command:
    return Command(id=command_id, title=title, keywords=("example",), run=_noop, shortcut=shortcut)


def _palette_payload(hotkey_hint: str | None) -> dict[str, object]:
    return {
        "enabled": True,
        "query": "save",
        "dirty": False,
        "rev": 1,
        "armed": False,
        "undo": 0,
        "redo": 0,
        "active_mode": "none",
        "prompt_active": False,
        "rows": [
            {
                "kind": "command",
                "id": "editor.scene.save",
                "title": "Save Scene",
                "hotkey_hint": hotkey_hint,
                "enabled": True,
                "disabled_reason": "",
            },
        ],
        "selected_row": 0,
    }


def _provider_payload(monkeypatch: pytest.MonkeyPatch, command: Command) -> dict[str, object]:
    monkeypatch.setattr("engine.editor_commands.get_all_commands", lambda _window: [command])
    monkeypatch.setattr("engine.editor_commands.filter_commands", lambda commands, _query, focus_target=None: list(commands))
    monkeypatch.setattr("engine.editor_commands.get_palette_focus_target", lambda _window: None)
    monkeypatch.setattr("engine.editor.editor_panels_query.panels_is_open", lambda _editor, _panel: True)
    window = SimpleNamespace(
        editor_controller=SimpleNamespace(
            active=True,
            search=SimpleNamespace(get_command_palette_state=lambda: ("save", 0)),
        )
    )
    return editor_command_palette_provider(window)


def test_command_dataclass_accepts_optional_shortcut() -> None:
    assert _command(shortcut="Ctrl+K").shortcut == "Ctrl+K"
    assert _command().shortcut is None


def test_overlay_renders_shortcut_badge_right_aligned() -> None:
    line = format_command_palette_overlay_lines(_palette_payload("Ctrl+S"))[1]

    assert "Save Scene" in line
    assert line.rstrip().endswith("Ctrl+S")


def test_overlay_omits_empty_shortcut_badge_without_none_literal() -> None:
    line = format_command_palette_overlay_lines(_palette_payload(None))[1]

    assert line == "> Save Scene"
    assert "None" not in line


def test_editor_provider_passes_command_shortcut_to_overlay_row(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _provider_payload(monkeypatch, _command("editor.scene.save", "Save Scene", "Ctrl+S"))

    assert payload["rows"][0]["hotkey_hint"] == "Ctrl+S"


def test_editor_provider_omits_none_shortcut_badge(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _provider_payload(monkeypatch, _command("editor.custom", "Custom Command"))

    assert payload["rows"][0]["hotkey_hint"] == ""


def test_locked_high_frequency_commands_have_shortcut_badges() -> None:
    commands = {command.id: command.shortcut for command in get_all_commands(None)}

    assert {
        "editor.scene.save": "Ctrl+S",
        "editor.scene_browser.open": "Ctrl+Shift+O",
        "editor.scene_switcher.toggle": "Ctrl+O",
        "editor.history.undo": "Ctrl+Z",
        "editor.history.redo": "Ctrl+Y",
        "editor.keybinds.open": "Ctrl+Alt+K",
        "editor.light_tool.toggle": "L",
        "editor.occluder_tool.toggle": "O",
        "editor.entity_panels.toggle": "Ctrl+E",
        "editor.panel.project_explorer.toggle": "Ctrl+Alt+4",
        "editor.panel.problems.toggle": "Ctrl+Alt+3",
        "editor.play.start": "F6",
    }.items() <= commands.items()


def test_unpopulated_command_has_no_shortcut_badge() -> None:
    commands = {command.id: command.shortcut for command in get_all_commands(None)}

    assert commands["editor.lighting_preset.1"] is None


def test_shortcut_field_does_not_change_fuzzy_ranking() -> None:
    commands = [
        _command("editor.copy.generic", "Copy", "Ctrl+Shift+G"),
        Command(
            id="editor.project_explorer.copy_path",
            title="Project Explorer: Copy Selected Paths",
            keywords=("project", "explorer", "copy", "path"),
            run=_noop,
            shortcut="Ctrl+Shift+C",
        ),
    ]

    assert [command.id for command in filter_commands(commands, "copy")] == [
        "editor.copy.generic",
        "editor.project_explorer.copy_path",
    ]
