from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.fast


def test_build_command_help_rows_is_deterministic_for_known_command() -> None:
    from engine.command_palette_help import build_command_help_rows

    first = build_command_help_rows(
        "selection.align",
        command_title="Selection: Align...",
        command_section="Selection",
    )
    second = build_command_help_rows(
        "selection.align",
        command_title="Selection: Align...",
        command_section="Selection",
    )
    assert first == second
    assert "keys: Up/Down navigate" in first
    assert "keys: Enter insert/execute" in first
    assert "keys: Ctrl+Up/Ctrl+Down prompt history" in first
    assert "command: selection.align" in first
    assert "title: Selection: Align..." in first
    assert "section: Selection" in first
    assert any(line.startswith("description: ") for line in first)
    assert "examples:" in first
    assert "accepted args:" in first


def test_help_toggle_is_palette_scoped() -> None:
    from engine.command_palette_controller import handle_command_palette_toggle_help

    window = SimpleNamespace(command_palette_enabled=True, command_palette_help_enabled=False)
    assert handle_command_palette_toggle_help(window) is True
    assert window.command_palette_help_enabled is True
    assert handle_command_palette_toggle_help(window) is True
    assert window.command_palette_help_enabled is False

    disabled = SimpleNamespace(command_palette_enabled=False, command_palette_help_enabled=False)
    assert handle_command_palette_toggle_help(disabled) is False
    assert disabled.command_palette_help_enabled is False


def test_overlay_renders_help_rows_when_enabled() -> None:
    from engine.ui_overlays.command_palette import format_command_palette_overlay_lines

    payload = {
        "enabled": True,
        "query": "",
        "dirty": False,
        "rev": 1,
        "armed": False,
        "undo": 0,
        "redo": 0,
        "active_mode": "none",
        "help_enabled": True,
        "help_rows": [
            "keys: Up/Down navigate",
            "command: selection.align",
            "description: Align selected entities on an axis.",
        ],
    }
    lines = format_command_palette_overlay_lines(payload)
    assert "HELP VIEW (F1 to close)" in lines
    assert "command: selection.align" in lines
    assert "description: Align selected entities on an axis." in lines


def test_f1_route_registered_for_command_palette_help_toggle() -> None:
    import engine.optional_arcade as optional_arcade
    from engine.input_runtime.capture_key_router_model import (
        SCOPE_COMMAND_PALETTE,
        build_route_table,
    )

    key = optional_arcade.arcade.key
    routes = [r for r in build_route_table() if r.scope == SCOPE_COMMAND_PALETTE]
    matches = [
        r
        for r in routes
        if r.action_id == "capture.command_palette.help_toggle"
        and int(r.combo.key) == int(key.F1)
        and int(r.combo.mods) == 0
    ]
    assert matches
