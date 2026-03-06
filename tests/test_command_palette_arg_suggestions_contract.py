from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.command_palette_controller import handle_command_palette_activate
from engine.command_palette_preview import build_arg_suggestions
from engine.ui_overlays.command_palette import format_command_palette_overlay_lines
from engine.ui_overlays.providers import command_palette_provider

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("command_id", "raw_arg"),
    [
        ("selection.align", ""),
        ("selection.distribute", ""),
        ("selection.snap_to_grid", ""),
        ("selection.nudge", ""),
        ("selection.rotate", ""),
    ],
)
def test_suggestions_exist_for_supported_commands(command_id: str, raw_arg: str) -> None:
    suggestions = build_arg_suggestions(command_id, raw_arg)
    assert suggestions


def test_suggestions_narrow_for_partial_input() -> None:
    suggestions = build_arg_suggestions("selection.align", "le")
    assert suggestions
    assert suggestions[0] == "left"
    assert all("le" in item.lower() for item in suggestions)


def test_unknown_command_returns_empty_suggestions() -> None:
    assert build_arg_suggestions("selection.scatter", "n=10") == []


def test_overlay_renders_suggestions_for_text_prompt() -> None:
    payload = {
        "enabled": True,
        "query": "selection",
        "dirty": False,
        "rev": 1,
        "armed": False,
        "undo": 0,
        "redo": 0,
        "active_mode": "none",
        "prompt_active": True,
        "prompt_kind": "text",
        "prompt_title": "Selection: Align…",
        "prompt_text": "le",
        "prompt_rows": [
            {"value": "left", "label": "left"},
            {"value": "axis=x|mode=left|reference=primary", "label": "axis=x|mode=left|reference=primary"},
        ],
        "prompt_selected_row": 0,
    }
    lines = format_command_palette_overlay_lines(payload)
    assert "Suggestions:" in lines
    assert "> left" in lines


def test_provider_includes_prompt_suggestions_for_text_prompt() -> None:
    window = SimpleNamespace(
        show_debug=True,
        command_palette_enabled=True,
        command_palette_query="align",
        command_palette_index=0,
        command_palette_prompt_active=True,
        command_palette_prompt_text="le",
        command_palette_prompt_kind="text",
        command_palette_prompt_query="",
        command_palette_prompt_index=0,
        command_palette_prompt_placeholder="left / center / right",
        command_palette_prompt_title="Selection: Align…",
        command_palette_prompt_command_id="selection.align",
        command_palette_prompt_steps=(),
        command_palette_prompt_step_index=0,
        scene_dirty=False,
        scene_dirty_counter=0,
        scene_persist_armed=False,
        undo_stack=[],
        redo_stack=[],
        capture_state=None,
        entity_paint_state=None,
        tile_paint_state=None,
    )
    payload = command_palette_provider(window)
    rows = payload.get("prompt_rows")
    assert isinstance(rows, list)
    assert rows
    assert rows[0]["value"] == "left"


def test_activate_inserts_selected_suggestion_before_execute() -> None:
    window = SimpleNamespace(
        show_debug=True,
        command_palette_enabled=True,
        command_palette_prompt_active=True,
        command_palette_prompt_command_id="selection.align",
        command_palette_prompt_steps=(),
        command_palette_prompt_step_index=0,
        command_palette_prompt_values={},
        command_palette_prompt_text="le",
        command_palette_prompt_kind="text",
        command_palette_prompt_index=0,
        command_palette_prompt_query="",
        command_palette_query="align",
        command_palette_index=0,
    )
    consumed = handle_command_palette_activate(window, snapshot=SimpleNamespace(), repeat=False)
    assert consumed is True
    assert window.command_palette_prompt_text == "left"
    assert window.command_palette_prompt_active is True
