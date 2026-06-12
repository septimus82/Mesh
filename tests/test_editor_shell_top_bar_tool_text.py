from __future__ import annotations

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.fast


def _tool_move_width() -> float:
    return len("Tool: MOVE") * 12.0 * 0.58


def test_tool_text_rect_does_not_overlap_top_bar_controls_across_widths() -> None:
    from engine.editor.editor_shell_layout import (
        compute_editor_shell_layout,
        compute_top_bar_controls,
        compute_top_bar_tool_text_rect,
    )

    for width in (480, 800, 1280, 1600):
        layout = compute_editor_shell_layout(width, 720, 320, 320)
        controls = compute_top_bar_controls(layout)
        tool_rect = compute_top_bar_tool_text_rect(layout, _tool_move_width())

        for button_rect in (controls.toggle_left, controls.toggle_right, controls.toggle_max):
            assert tool_rect.right <= button_rect.left or tool_rect.left >= button_rect.right


def test_top_bar_control_rects_match_golden_positions() -> None:
    from engine.editor.editor_shell_layout import compute_editor_shell_layout, compute_top_bar_controls

    controls = compute_top_bar_controls(compute_editor_shell_layout(1280, 720, 320, 320))

    assert (controls.toggle_left.left, controls.toggle_left.right) == (1140.0, 1168.0)
    assert (controls.toggle_right.left, controls.toggle_right.right) == (1172.0, 1200.0)
    assert (controls.toggle_max.left, controls.toggle_max.right) == (1204.0, 1232.0)


def test_tool_text_rect_ends_before_left_toggle_with_expected_margin() -> None:
    from engine.editor.editor_shell_layout import (
        TOP_BAR_BUTTON_MARGIN,
        compute_editor_shell_layout,
        compute_top_bar_controls,
        compute_top_bar_tool_text_rect,
    )

    layout = compute_editor_shell_layout(1280, 720, 320, 320)
    controls = compute_top_bar_controls(layout)
    tool_rect = compute_top_bar_tool_text_rect(layout, _tool_move_width())

    assert controls.toggle_left.left - tool_rect.right == TOP_BAR_BUTTON_MARGIN


def test_editor_shell_overlay_draws_tool_text_at_layout_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    import engine.ui_overlays.editor_shell_overlay as overlay_module
    from engine.editor.editor_shell_layout import (
        compute_editor_shell_layout,
        compute_top_bar_tool_text_rect,
    )

    captured: list[tuple[str, float]] = []

    monkeypatch.setattr(overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        overlay_module,
        "draw_text_cached",
        lambda text, x, *args, **kwargs: captured.append((str(text), float(x))),
    )

    overlay = overlay_module.EditorShellOverlay(SimpleNamespace(scene_controller=None))
    layout = compute_editor_shell_layout(1280, 720, 320, 320)
    controller = SimpleNamespace(tool_mode="MOVE", scene_dirty=False)

    overlay._draw_top_bar(layout, controller, object())

    tool_x = next(x for text, x in captured if text == "Tool: MOVE")
    expected_rect = compute_top_bar_tool_text_rect(layout, _tool_move_width())
    assert tool_x == expected_rect.right
