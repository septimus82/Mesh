from __future__ import annotations

import pytest

from engine.ui_overlays.widgets import Rect, TextInput

pytestmark = [pytest.mark.fast]


def _instruction_kinds(widget: TextInput) -> list[str]:
    return [instruction.kind for instruction in widget.render()]


def test_textinput_typing_backspace_deterministic() -> None:
    widget = TextInput(text="", placeholder="Search", focused=True)
    widget.layout(Rect(x=10.0, y=20.0, width=240.0, height=24.0))

    assert widget.on_text_input("a") is True
    assert widget.on_text_input("b") is True
    assert widget.text == "ab"
    assert widget.on_key_backspace() is True
    assert widget.text == "a"

    first = widget.render()
    second = widget.render()
    assert first == second


def test_textinput_focus_hit_test() -> None:
    widget = TextInput(text="", placeholder="", focused=False)
    widget.layout(Rect(x=100.0, y=200.0, width=120.0, height=20.0))

    changed_inside = widget.on_mouse_press(120.0, 210.0)
    assert changed_inside is True
    assert widget.focused is True

    changed_outside = widget.on_mouse_press(20.0, 20.0)
    assert changed_outside is True
    assert widget.focused is False


def test_textinput_renders_caret_only_when_focused() -> None:
    widget = TextInput(text="hello", placeholder="Search", focused=True)
    widget.layout(Rect(x=0.0, y=0.0, width=200.0, height=20.0))
    assert "text_input_caret" in _instruction_kinds(widget)

    widget.focused = False
    widget.layout(Rect(x=0.0, y=0.0, width=200.0, height=20.0))
    assert "text_input_caret" not in _instruction_kinds(widget)
