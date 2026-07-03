from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.ui_controller import UIController, creator_mode_hiding_editor_chrome
from engine.ui_overlays.common import UIElement

pytestmark = pytest.mark.fast


class _TrackingElement(UIElement):
    def __init__(self, window, *, editor_chrome: bool = True) -> None:
        super().__init__(window, editor_chrome=editor_chrome)
        self.draw_calls = 0

    def draw(self) -> None:
        self.draw_calls += 1


def _make_window(*, creator_active: bool, editor_active: bool = True) -> SimpleNamespace:
    creator_mode = SimpleNamespace(active=creator_active)
    editor_controller = SimpleNamespace(active=editor_active, creator_mode=creator_mode)
    window = SimpleNamespace(editor_controller=editor_controller)
    window.ui_controller = UIController(window)
    return window


def test_creator_mode_hiding_editor_chrome_requires_active_editor() -> None:
    window = _make_window(creator_active=True, editor_active=False)
    assert creator_mode_hiding_editor_chrome(window) is False


def test_creator_mode_hiding_editor_chrome_when_creator_active() -> None:
    window = _make_window(creator_active=True)
    assert creator_mode_hiding_editor_chrome(window) is True


def test_creator_mode_hiding_editor_chrome_when_creator_inactive() -> None:
    window = _make_window(creator_active=False)
    assert creator_mode_hiding_editor_chrome(window) is False


def test_ui_controller_draw_suppresses_editor_chrome_under_creator_mode() -> None:
    window = _make_window(creator_active=True)
    chrome = _TrackingElement(window, editor_chrome=True)
    gameplay = _TrackingElement(window, editor_chrome=False)
    window.ui_controller.register_ui_element(chrome)
    window.ui_controller.register_ui_element(gameplay)

    window.ui_controller.draw()

    assert chrome.draw_calls == 0
    assert gameplay.draw_calls == 1


def test_ui_controller_draw_draws_all_elements_when_creator_inactive() -> None:
    window = _make_window(creator_active=False)
    chrome = _TrackingElement(window, editor_chrome=True)
    gameplay = _TrackingElement(window, editor_chrome=False)
    window.ui_controller.register_ui_element(chrome)
    window.ui_controller.register_ui_element(gameplay)

    window.ui_controller.draw()

    assert chrome.draw_calls == 1
    assert gameplay.draw_calls == 1


def test_register_ui_element_can_override_editor_chrome_flag() -> None:
    window = _make_window(creator_active=True)
    element = _TrackingElement(window, editor_chrome=True)
    window.ui_controller.register_ui_element(element, editor_chrome=False)

    window.ui_controller.draw()

    assert element.draw_calls == 1


def test_ui_controller_draw_suppresses_many_editor_chrome_elements() -> None:
    window = _make_window(creator_active=True)
    chrome_elements = [_TrackingElement(window, editor_chrome=True) for _ in range(12)]
    gameplay_elements = [_TrackingElement(window, editor_chrome=False) for _ in range(7)]
    for element in chrome_elements + gameplay_elements:
        window.ui_controller.register_ui_element(element)

    window.ui_controller.draw()

    assert all(element.draw_calls == 0 for element in chrome_elements)
    assert all(element.draw_calls == 1 for element in gameplay_elements)


def test_ui_dispatcher_universal_overlays_registered_without_editor_chrome() -> None:
    from pathlib import Path

    source = Path("engine/game_parts/ui_dispatcher.py").read_text(encoding="utf-8")
    universal_attrs = (
        "interact_prompt_overlay",
        "objective_tracker_overlay",
        "demo_complete_overlay",
        "main_menu_overlay",
        "settings_overlay",
        "fog_overlay",
        "transition_fade_overlay",
    )
    for attr in universal_attrs:
        assert f"register_ui_element(window.{attr}, editor_chrome=False)" in source, attr

    assert "register_ui_element(window.editor_shell_overlay)" in source
    assert "register_ui_element(window.editor_shell_overlay, editor_chrome=False)" not in source
