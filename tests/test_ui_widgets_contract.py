from __future__ import annotations

import pytest

from engine.ui_overlays.widgets import Button, Label, Padding, Panel, Rect, VStack

pytestmark = [pytest.mark.fast]


def _instruction_signature(layout) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
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


def test_widget_layout_is_deterministic() -> None:
    bounds = Rect(x=100.0, y=200.0, width=320.0, height=240.0)
    root = Panel(
        children=[
            VStack(
                children=[
                    Label(text="TITLE", font_size=24, height=40.0),
                    Button(text="Play", action_id="pause.main.0", font_size=18, height=34.0, text_color_token="yellow"),
                    Button(text="Quit", action_id="pause.main.1", font_size=18, height=34.0, text_color_token="gray"),
                ],
                spacing=6.0,
                align="center",
            )
        ],
        padding=Padding.uniform(12.0),
        bg_style_token="panel",
    )
    first = root.layout(bounds)
    second = root.layout(bounds)
    assert _instruction_signature(first) == _instruction_signature(second)


def test_button_hit_test_uses_layout_rect() -> None:
    button = Button(text="Resume", action_id="pause.main.0", height=30.0)
    button.layout(Rect(x=10.0, y=20.0, width=120.0, height=30.0))
    assert button.hit_test(10.0, 20.0) is True
    assert button.hit_test(130.0, 50.0) is True
    assert button.hit_test(9.99, 20.0) is False
    assert button.hit_test(130.01, 50.0) is False
