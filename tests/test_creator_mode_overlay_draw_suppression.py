from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_overlay_controller import EditorOverlayController

pytestmark = pytest.mark.fast


def test_creator_mode_active_suppresses_advanced_editor_draw_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _make_editor(creator_active=True)
    controller = EditorOverlayController(editor)
    draw_creator = MagicMock()
    monkeypatch.setattr(
        "engine.editor.creator_mode.creator_overlay_renderer.draw_creator_overlay",
        draw_creator,
    )

    controller.draw_overlay()

    draw_creator.assert_called_once_with(editor)
    editor.ui_layers.draw_all.assert_not_called()
    editor.panels.draw_panels.assert_not_called()
    editor.hierarchy.draw_hierarchy_panel.assert_not_called()
    editor.palette.draw_palette.assert_not_called()
    editor.dialogue.draw_dialogue_panel.assert_not_called()
    editor.dialogue.draw_quest_context_panel.assert_not_called()
    editor.animation.draw_animation_panel_if_active.assert_not_called()
    editor.tile.draw_tile_panel_if_active.assert_not_called()
    editor.debug_overlay.draw_debug_overlay.assert_not_called()


def test_creator_mode_inactive_draws_advanced_editor_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _make_editor(creator_active=False)
    controller = EditorOverlayController(editor)
    draw_creator = MagicMock()
    monkeypatch.setattr(
        "engine.editor.creator_mode.creator_overlay_renderer.draw_creator_overlay",
        draw_creator,
    )
    monkeypatch.setattr(controller, "_draw_tour_overlay", MagicMock())

    controller.draw_overlay()

    draw_creator.assert_not_called()
    editor.panels.draw_panels.assert_called_once()
    editor.ui_layers.draw_all.assert_not_called()
    editor.hierarchy.draw_hierarchy_panel.assert_not_called()


def test_creator_mode_active_still_draws_unsaved_confirm_modal(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _make_editor(creator_active=True)
    controller = EditorOverlayController(editor)
    monkeypatch.setattr(
        "engine.editor.creator_mode.creator_overlay_renderer.draw_creator_overlay",
        MagicMock(),
    )

    controller.draw_overlay()

    editor.unsaved_confirm.draw.assert_called_once()


def _make_editor(*, creator_active: bool) -> SimpleNamespace:
    window = SimpleNamespace(width=1280, height=720, editor_shell_overlay=object())
    creator_mode = SimpleNamespace(active=creator_active)
    editor = SimpleNamespace(
        active=True,
        window=window,
        creator_mode=creator_mode,
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
