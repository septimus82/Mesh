from __future__ import annotations

import pytest

from engine.ui_overlays.widgets import Rect, Toggle

pytestmark = [pytest.mark.fast]


def _instruction_signature(toggle: Toggle, bounds: Rect) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    layout = toggle.layout(bounds)
    rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for item in layout.instructions:
        payload_pairs = tuple(
            sorted((str(key), repr(value)) for key, value in item.payload.items())
        )
        rows.append((item.kind, payload_pairs))
    return rows


def test_toggle_layout_deterministic() -> None:
    toggle = Toggle(label="Rumble Enabled", value=True)
    bounds = Rect(x=12.0, y=18.0, width=260.0, height=22.0)
    assert _instruction_signature(toggle, bounds) == _instruction_signature(toggle, bounds)


def test_toggle_click_toggles_when_hit() -> None:
    toggle = Toggle(label="Rumble Enabled", value=False)
    bounds = Rect(x=0.0, y=0.0, width=100.0, height=20.0)
    toggle.layout(bounds)
    assert toggle.on_mouse_press(25.0, 10.0) is True
    assert toggle.value is True
    assert toggle.on_mouse_press(25.0, 10.0) is True
    assert toggle.value is False


def test_toggle_click_outside_does_not_toggle() -> None:
    toggle = Toggle(label="Rumble Enabled", value=False)
    bounds = Rect(x=0.0, y=0.0, width=100.0, height=20.0)
    toggle.layout(bounds)
    assert toggle.on_mouse_press(150.0, 10.0) is False
    assert toggle.value is False

