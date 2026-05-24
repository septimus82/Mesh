from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor.editor_shell_layout import DockTabState, compute_editor_shell_layout
from engine.text_draw import TextCache
from engine.ui_overlays import editor_shell_overlay
from engine.ui_overlays.editor_shell_overlay import EditorShellOverlay, truncate_tab_label

pytestmark = pytest.mark.fast


def test_truncate_tab_label_full_fits() -> None:
    assert truncate_tab_label("Inspector", 200.0, font_size=11.0) == "Inspector"


def test_truncate_tab_label_narrow_truncates() -> None:
    result = truncate_tab_label("Inspector", 30.0, font_size=11.0)

    assert result.endswith("...")
    assert len(result) < len("Inspector")


def test_overlay_draws_truncated_label_for_narrow_right_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn_text: list[str] = []

    def _capture_text(text: str, *_args: object, **_kwargs: object) -> None:
        drawn_text.append(str(text))

    monkeypatch.setattr(editor_shell_overlay, "draw_text_cached", _capture_text)
    monkeypatch.setattr(editor_shell_overlay, "draw_panel_bg", lambda *_args, **_kwargs: None)

    overlay = EditorShellOverlay(SimpleNamespace())
    layout = compute_editor_shell_layout(1280, 720, 320, 320)

    overlay._draw_right_dock(layout, DockTabState(right_tab="Inspector"), TextCache())

    assert "Inspector" not in drawn_text
    assert any(label.endswith("...") for label in drawn_text)
    assert "Debug" in drawn_text
