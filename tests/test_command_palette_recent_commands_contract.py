from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.command_palette_controller import (
    CommandPaletteRecentCommands,
    get_command_palette_recent_command_ids,
    handle_command_palette_activate,
)
from engine.ui_overlays.providers import command_palette_provider

pytestmark = pytest.mark.fast


def _make_command(
    cmd_id: str,
    title: str,
    action: object,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=cmd_id,
        title=title,
        section="Selection",
        keywords=("selection",),
        prompt=None,
        prompts=None,
        macro_id="",
        hotkey_hint=None,
        is_enabled=lambda _window: (True, ""),
        action=action,
    )


def _make_window() -> SimpleNamespace:
    return SimpleNamespace(
        show_debug=True,
        command_palette_enabled=True,
        command_palette_help_enabled=False,
        command_palette_prompt_active=False,
        command_palette_query="",
        command_palette_index=0,
        scene_dirty=False,
        scene_dirty_counter=0,
        scene_persist_armed=False,
        undo_stack=[],
        redo_stack=[],
        capture_state=None,
        entity_paint_state=None,
        tile_paint_state=None,
    )


def test_recent_commands_update_on_successful_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.command_palette as palette_mod

    calls: list[str] = []
    cmds = [
        _make_command("cmd.a", "Cmd A", lambda _w, _arg: calls.append("a")),
        _make_command("cmd.b", "Cmd B", lambda _w, _arg: calls.append("b")),
        _make_command("cmd.c", "Cmd C", lambda _w, _arg: calls.append("c")),
    ]
    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(cmds))

    window = _make_window()
    window._command_palette_recent_commands = CommandPaletteRecentCommands(max_entries=2)

    for idx in (0, 1, 0, 2):
        window.command_palette_enabled = True
        window.command_palette_index = idx
        handled = handle_command_palette_activate(window, snapshot=SimpleNamespace(), repeat=False)
        assert handled is True

    assert calls == ["a", "b", "a", "c"]
    assert get_command_palette_recent_command_ids(window) == ("cmd.c", "cmd.a")


def test_recent_commands_do_not_update_on_failed_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.command_palette as palette_mod

    def _raise_action(_window: object, _arg: str | None) -> None:
        raise RuntimeError("boom")

    cmds = [_make_command("cmd.fail", "Cmd Fail", _raise_action)]
    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(cmds))

    window = _make_window()
    window.command_palette_enabled = True
    window.command_palette_index = 0
    handled = handle_command_palette_activate(window, snapshot=SimpleNamespace(), repeat=False)
    assert handled is True
    assert get_command_palette_recent_command_ids(window) == ()


def test_provider_includes_recent_section_in_deterministic_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.command_palette as palette_mod

    cmds = [
        _make_command("cmd.a", "Cmd A", lambda _w, _arg: None),
        _make_command("cmd.b", "Cmd B", lambda _w, _arg: None),
        _make_command("cmd.c", "Cmd C", lambda _w, _arg: None),
    ]
    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(cmds))

    window = _make_window()
    window._command_palette_recent_commands = CommandPaletteRecentCommands(
        max_entries=12,
        command_ids=["cmd.c", "cmd.a"],
    )
    payload = command_palette_provider(window)
    rows = payload.get("rows")
    assert isinstance(rows, list)
    assert rows[0] == {"kind": "section", "title": "Recent"}
    assert rows[1]["kind"] == "command"
    assert rows[1]["id"] == "cmd.c"
    assert rows[2]["kind"] == "command"
    assert rows[2]["id"] == "cmd.a"
    assert payload.get("selected_row") == 2
