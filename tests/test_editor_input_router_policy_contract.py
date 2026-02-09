from __future__ import annotations

import inspect
from pathlib import Path

from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_PROJECT_EXPLORER,
    SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
)
from engine.editor_runtime import editor_input_router_model as model
from engine.editor_runtime import input as editor_input


def test_handle_input_is_thin() -> None:
    source = inspect.getsource(editor_input.handle_input)
    assert len(source.splitlines()) <= 250


def test_router_modules_do_not_import_editor_actions() -> None:
    base = Path("engine/editor_runtime")
    for filename in ("editor_input_router.py", "editor_input_router_model.py"):
        text = (base / filename).read_text(encoding="utf-8")
        assert "editor_actions" not in text


def test_command_palette_logic_not_in_router() -> None:
    text = Path("engine/editor_runtime/editor_input_router.py").read_text(encoding="utf-8")
    forbidden = (
        "command_palette_query",
        "command_palette_index",
        "filter_commands",
        "get_all_commands",
        "get_palette_focus_target",
    )
    for token in forbidden:
        assert token not in text, f"{token} should not be in editor_input_router.py"


def test_route_table_minimum_scopes() -> None:
    routes = model.build_route_table()
    scopes = {route.scope for route in routes}
    assert model.SCOPE_COMMAND_PALETTE in scopes
    assert SHORTCUT_SCOPE_PROJECT_EXPLORER in scopes
    assert SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU in scopes
    assert SHORTCUT_SCOPE_GLOBAL in scopes
