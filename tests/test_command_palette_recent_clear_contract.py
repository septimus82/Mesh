from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.command_palette_controller import (
    CommandPaletteRecentCommands,
    clear_command_palette_recent_commands,
    get_command_palette_recent_command_ids,
    handle_command_palette_navigate,
)
from engine.ui_overlays.providers import command_palette_provider

pytestmark = pytest.mark.fast


def _make_cmd(cmd_id: str, title: str) -> SimpleNamespace:
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
        action=lambda _window, _arg: None,
    )


def _window() -> SimpleNamespace:
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


def test_palette_clear_recent_command_id_present() -> None:
    from engine.command_palette import build_default_commands

    ids = [c.id for c in build_default_commands(object())]
    assert "palette.clear_recent" in ids


def test_clear_recent_removes_recent_section_and_keeps_main_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.command_palette as palette_mod

    cmds = [
        _make_cmd("cmd.a", "Cmd A"),
        _make_cmd("cmd.b", "Cmd B"),
        _make_cmd("cmd.c", "Cmd C"),
    ]
    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(cmds))

    window = _window()
    window._command_palette_recent_commands = CommandPaletteRecentCommands(
        max_entries=12,
        command_ids=["cmd.c", "cmd.a"],
    )

    before = command_palette_provider(window)
    rows_before = before["rows"]
    assert rows_before[0] == {"kind": "section", "title": "Recent"}
    # Main-list order remains unchanged after Recent section.
    section_idx = next(i for i, row in enumerate(rows_before) if row.get("kind") == "section" and row.get("title") == "Selection")
    main_ids_before = [row["id"] for row in rows_before[section_idx + 1 :] if row.get("kind") == "command"]
    assert main_ids_before == ["cmd.a", "cmd.b", "cmd.c"]

    removed = clear_command_palette_recent_commands(window)
    assert removed == 2
    assert get_command_palette_recent_command_ids(window) == ()

    after = command_palette_provider(window)
    rows_after = after["rows"]
    assert rows_after[0] == {"kind": "section", "title": "Selection"}
    main_ids_after = [row["id"] for row in rows_after[1:] if row.get("kind") == "command"]
    assert main_ids_after == ["cmd.a", "cmd.b", "cmd.c"]


def test_selection_stable_with_recent_section_and_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.command_palette as palette_mod

    cmds = [
        _make_cmd("cmd.a", "Cmd A"),
        _make_cmd("cmd.b", "Cmd B"),
        _make_cmd("cmd.c", "Cmd C"),
    ]
    monkeypatch.setattr(palette_mod, "build_default_commands", lambda _window: list(cmds))

    window = _window()
    window._command_palette_recent_commands = CommandPaletteRecentCommands(
        max_entries=12,
        command_ids=["cmd.c", "cmd.a"],
    )

    payload0 = command_palette_provider(window)
    # Default selected command remains first item in the main list (cmd.a),
    # offset by the count of recent command rows.
    assert payload0["selected_row"] == 2

    assert handle_command_palette_navigate(window, 1) is True
    payload1 = command_palette_provider(window)
    assert payload1["selected_row"] == 3
