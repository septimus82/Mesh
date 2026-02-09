from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_panels_query import panels_active_modal, panels_is_open


def test_panels_is_open_prefers_panels() -> None:
    panels = SimpleNamespace(is_command_palette_open=lambda: True)
    ui_layers = SimpleNamespace(is_visible=lambda _layer: False)
    editor = SimpleNamespace(panels=panels, ui_layers=ui_layers)

    assert panels_is_open(editor, "command_palette") is True


def test_panels_is_open_falls_back_to_ui_layers() -> None:
    ui_layers = SimpleNamespace(is_visible=lambda _layer: True)
    editor = SimpleNamespace(ui_layers=ui_layers)

    assert panels_is_open(editor, "command_palette") is True


def test_panels_is_open_unsaved_confirm() -> None:
    editor = SimpleNamespace(unsaved_confirm=SimpleNamespace(is_open=True))

    assert panels_is_open(editor, "unsaved_confirm") is True


def test_panels_active_modal_uses_panels_ui_layers() -> None:
    ui_layers = SimpleNamespace(_state=SimpleNamespace(active_modal_id="confirm_modal"))
    panels = SimpleNamespace(ui_layers=ui_layers)
    editor = SimpleNamespace(panels=panels)

    assert panels_active_modal(editor) == "confirm_modal"


def test_panels_active_modal_falls_back_to_editor_ui_layers() -> None:
    ui_layers = SimpleNamespace(_state=SimpleNamespace(active_modal_id="context_menu"))
    editor = SimpleNamespace(ui_layers=ui_layers)

    assert panels_active_modal(editor) == "context_menu"
