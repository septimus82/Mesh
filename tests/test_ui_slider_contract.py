from __future__ import annotations

import pytest

from engine.ui_overlays.widgets import Rect, Slider

pytestmark = [pytest.mark.fast]


def _instruction_signature(slider: Slider, bounds: Rect) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    layout = slider.layout(bounds)
    rows: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for item in layout.instructions:
        payload_pairs = tuple(
            sorted(
                (
                    str(key),
                    (
                        repr(value)
                        if key != "rect"
                        else f"Rect({value.x:.2f},{value.y:.2f},{value.width:.2f},{value.height:.2f})"
                    ),
                )
                for key, value in item.payload.items()
            )
        )
        rows.append((item.kind, payload_pairs))
    return rows


def test_slider_layout_deterministic() -> None:
    slider = Slider(label="SFX Volume", value=0.4, step=0.01)
    bounds = Rect(x=20.0, y=30.0, width=240.0, height=28.0)
    first = _instruction_signature(slider, bounds)
    second = _instruction_signature(slider, bounds)
    assert first == second


def test_slider_visuals_stay_inside_row_bounds_at_extremes() -> None:
    bounds = Rect(x=20.0, y=30.0, width=240.0, height=28.0)
    for value in (0.0, 1.0):
        slider = Slider(label="SFX Volume", value=value, step=0.01)
        layout = slider.layout(bounds)
        rects = [
            instruction.payload["rect"]
            for instruction in layout.instructions
            if instruction.kind in {"slider_track", "slider_fill", "slider_knob"}
        ]

        assert rects
        for rect in rects:
            assert bounds.left <= rect.left <= rect.right <= bounds.right


def test_slider_click_sets_value() -> None:
    slider = Slider(label="SFX", value=0.0, step=0.01)
    bounds = Rect(x=0.0, y=0.0, width=100.0, height=20.0)
    slider.layout(bounds)
    handled = slider.on_mouse_press(75.0, 10.0)
    assert handled is True
    assert slider.value == pytest.approx(0.75, abs=1e-9)


def test_slider_drag_clamps_and_respects_step() -> None:
    slider = Slider(label="SFX", value=0.5, step=0.1)
    bounds = Rect(x=10.0, y=10.0, width=100.0, height=20.0)
    slider.layout(bounds)
    slider.on_mouse_press(10.0, 20.0)

    changed = slider.on_mouse_drag(64.0, 20.0)
    assert changed is True
    assert slider.value == pytest.approx(0.5, abs=1e-9)

    slider.on_mouse_drag(500.0, 20.0)
    assert slider.value == pytest.approx(1.0, abs=1e-9)

    slider.on_mouse_drag(-500.0, 20.0)
    assert slider.value == pytest.approx(0.0, abs=1e-9)

    assert slider.on_mouse_release(0.0, 0.0) is True
    assert slider.dragging is False
