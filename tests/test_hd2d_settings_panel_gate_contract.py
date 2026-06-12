from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_dock_controller import EditorDockController
from engine.ui_overlays.hd2d_settings_panel_overlay import Hd2dSettingsPanelOverlay

pytestmark = pytest.mark.fast


def _make_window(*, shell_active: bool) -> SimpleNamespace:
    controller = SimpleNamespace(
        active=True,
        dock=EditorDockController(None, right_tab="Inspector"),
        _primary_selected_id=None,
        _selected_entity_ids=[],
        _hd2d_panel_cursor_index=0,
        _hd2d_panel_sections_expanded={},
    )
    window = SimpleNamespace(
        width=800,
        height=600,
        editor_controller=controller,
    )
    if shell_active:
        window.editor_shell_overlay = object()
    return window


def test_hd2d_settings_panel_draw_skips_when_dock_shell_active(monkeypatch) -> None:
    overlay = Hd2dSettingsPanelOverlay(_make_window(shell_active=True))
    draw_panel = MagicMock()
    monkeypatch.setattr(overlay, "_draw_panel", draw_panel)

    overlay.draw()

    draw_panel.assert_not_called()


def test_hd2d_settings_panel_draw_preserved_when_dock_shell_absent(monkeypatch) -> None:
    overlay = Hd2dSettingsPanelOverlay(_make_window(shell_active=False))
    draw_panel = MagicMock()
    monkeypatch.setattr(overlay, "_draw_panel", draw_panel)

    overlay.draw()

    draw_panel.assert_called_once()
