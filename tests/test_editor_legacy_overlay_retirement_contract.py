from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_overlay_controller import EditorOverlayController
from engine.ui_overlays.light_occluder_editor import LightOccluderEditorOverlay

pytestmark = pytest.mark.fast


def _make_editor(*, shell_active: bool) -> SimpleNamespace:
    window = SimpleNamespace(width=800, height=600)
    if shell_active:
        window.editor_shell_overlay = object()
    editor = SimpleNamespace(
        active=True,
        window=window,
        build=SimpleNamespace(tick=MagicMock()),
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        _tick_workspace_autosave=MagicMock(),
        _update_status=MagicMock(),
        debug_overlay=SimpleNamespace(draw_debug_overlay=MagicMock()),
        _overlay_text_obj=object(),
        palette_active=False,
        palette=SimpleNamespace(draw_palette=MagicMock()),
        _palette_text_obj=object(),
        hierarchy=SimpleNamespace(draw_hierarchy_panel=MagicMock()),
        dialogue_panel_active=False,
        dialogue=SimpleNamespace(
            draw_dialogue_panel=MagicMock(),
            draw_quest_context_panel=MagicMock(),
        ),
        animation=SimpleNamespace(draw_animation_panel_if_active=MagicMock()),
        tile=SimpleNamespace(draw_tile_panel_if_active=MagicMock()),
        unsaved_confirm=SimpleNamespace(is_open=True, draw=MagicMock()),
        tour=SimpleNamespace(is_active=True),
        panels=SimpleNamespace(draw_panels=MagicMock()),
        ui_layers=SimpleNamespace(draw_all=MagicMock()),
    )
    window.editor_controller = editor
    return editor


def test_legacy_debug_and_hierarchy_hidden_when_dock_shell_active(monkeypatch) -> None:
    editor = _make_editor(shell_active=True)
    controller = EditorOverlayController(editor)
    tour_draw = MagicMock()
    monkeypatch.setattr(controller, "_draw_tour_overlay", tour_draw)

    controller.draw_overlay()

    editor.debug_overlay.draw_debug_overlay.assert_not_called()
    editor.hierarchy.draw_hierarchy_panel.assert_not_called()


def test_modals_tour_and_layer_panels_preserved_when_dock_shell_active(monkeypatch) -> None:
    editor = _make_editor(shell_active=True)
    controller = EditorOverlayController(editor)
    tour_draw = MagicMock()
    monkeypatch.setattr(controller, "_draw_tour_overlay", tour_draw)

    controller.draw_overlay()

    editor.unsaved_confirm.draw.assert_called_once()
    tour_draw.assert_called_once_with(editor.tour)
    editor.panels.draw_panels.assert_called_once()
    editor.ui_layers.draw_all.assert_not_called()
    editor.animation.draw_animation_panel_if_active.assert_called_once()
    editor.tile.draw_tile_panel_if_active.assert_called_once()


def test_legacy_debug_and_hierarchy_still_draw_when_dock_shell_absent(monkeypatch) -> None:
    editor = _make_editor(shell_active=False)
    controller = EditorOverlayController(editor)
    monkeypatch.setattr(controller, "_draw_tour_overlay", MagicMock())

    controller.draw_overlay()

    editor.debug_overlay.draw_debug_overlay.assert_called_once_with(editor._overlay_text_obj)
    editor.hierarchy.draw_hierarchy_panel.assert_called_once()


def test_light_occluder_screen_panel_hidden_when_dock_shell_active(monkeypatch) -> None:
    window = SimpleNamespace(width=800, height=600)
    window.editor_shell_overlay = object()
    window.editor_controller = SimpleNamespace(
        active=True,
        lights_tool_active=True,
        occluder_tool_active=False,
    )
    overlay = LightOccluderEditorOverlay(window)
    draw_background = MagicMock()
    draw_text = MagicMock()
    monkeypatch.setattr("engine.ui_overlays.light_occluder_editor._draw_rectangle_filled", draw_background)
    monkeypatch.setattr("engine.ui_overlays.light_occluder_editor.draw_text_cached", draw_text)

    overlay.draw()

    draw_background.assert_not_called()
    draw_text.assert_not_called()
