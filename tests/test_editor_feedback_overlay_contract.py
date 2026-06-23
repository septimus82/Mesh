from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor.editor_feedback_controller import EditorFeedbackController
from engine.editor.editor_feedback_model import FeedbackSeverity
from engine.ui_overlays.editor_feedback_overlay import EditorFeedbackOverlay

pytestmark = [pytest.mark.fast]


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


class _Controller:
    def __init__(self, clock: _Clock | None = None) -> None:
        self.active = True
        self._clock = clock or _Clock()
        self.feedback = EditorFeedbackController(self, clock=self._clock)

    def get_effective_dock_widths(self, _window_w: int) -> tuple[int, int]:
        return (320, 320)


def _make_window(clock: _Clock | None = None):
    controller = _Controller(clock)
    window = SimpleNamespace(
        width=1280,
        height=720,
        editor_controller=controller,
        text_cache=None,
    )
    return window, controller, controller._clock


def test_overlay_noops_without_editor() -> None:
    window = SimpleNamespace(width=1280, height=720, editor_controller=None, text_cache=None)
    overlay = EditorFeedbackOverlay(window)

    overlay.draw()

    assert overlay.get_visible_draw_items() == tuple()


def test_overlay_empty_queue_has_no_render_items() -> None:
    window, _controller, _clock = _make_window()
    overlay = EditorFeedbackOverlay(window)

    assert overlay.get_visible_draw_items() == tuple()


def test_overlay_layout_uses_viewport_top_right_inset() -> None:
    window, controller, clock = _make_window()
    overlay = EditorFeedbackOverlay(window)
    controller.feedback.info("One")

    items = overlay.get_visible_draw_items(now=clock.value)

    assert len(items) == 1
    item = items[0]
    assert item.right == pytest.approx(938.0)
    assert item.top == pytest.approx(656.0)
    assert item.left >= 518.0
    assert item.bottom < item.top


def test_overlay_limits_visible_entries_to_three_newest() -> None:
    window, controller, clock = _make_window()
    overlay = EditorFeedbackOverlay(window)
    for index in range(4):
        controller.feedback.info(f"msg-{index}", ttl=60.0)
        clock.value += 1.1

    items = overlay.get_visible_draw_items(now=clock.value)

    assert [item.text for item in items] == ["msg-1", "msg-2", "msg-3"]


def test_overlay_resolves_locked_severity_palette() -> None:
    window, controller, clock = _make_window()
    overlay = EditorFeedbackOverlay(window)
    controller.feedback.info("Info")
    controller.feedback.warning("Warn")
    controller.feedback.error("Error")

    items = overlay.get_visible_draw_items(now=clock.value)

    assert [item.bg_color[:3] for item in items] == [
        (22, 32, 42),
        (46, 36, 20),
        (50, 24, 28),
    ]
    assert [item.border_color[:3] for item in items] == [
        (94, 196, 255),
        (255, 196, 92),
        (255, 110, 110),
    ]


def test_overlay_fadeout_reaches_half_alpha_mid_window() -> None:
    window, controller, clock = _make_window()
    overlay = EditorFeedbackOverlay(window)
    controller.feedback.info("Fade", ttl=1.0)

    clock.value += 0.85
    items = overlay.get_visible_draw_items(now=clock.value)

    assert len(items) == 1
    assert items[0].alpha == pytest.approx(0.5, abs=0.05)

    clock.value += 0.15
    controller.feedback.tick(clock.value)
    assert overlay.get_visible_draw_items(now=clock.value) == tuple()


def test_overlay_formats_duplicate_count_suffix() -> None:
    window, controller, clock = _make_window()
    overlay = EditorFeedbackOverlay(window)
    controller.feedback.info("Repeat")
    clock.value += 0.5
    controller.feedback.info("Repeat")

    items = overlay.get_visible_draw_items(now=clock.value)

    assert items[0].text == "Repeat (×2)"


def test_overlay_exposes_severity_on_render_items() -> None:
    window, controller, clock = _make_window()
    overlay = EditorFeedbackOverlay(window)
    controller.feedback.warning("Warn")

    items = overlay.get_visible_draw_items(now=clock.value)

    assert items[0].severity is FeedbackSeverity.WARNING
