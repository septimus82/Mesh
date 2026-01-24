from __future__ import annotations

from dataclasses import dataclass

from engine.background_layers import BackgroundLayer, draw_background_layers


@dataclass(slots=True)
class DummyTexture:
    width: int = 64
    height: int = 32


def test_background_layers_repeat_tiling_does_not_crash_and_draws_multiple():
    calls: list[tuple[float, float, float, float]] = []

    def draw_stub(cx: float, cy: float, w: float, h: float, _tex: DummyTexture) -> None:
        calls.append((cx, cy, w, h))

    layers = [
        BackgroundLayer(
            id="Sky",
            path="assets/bg/sky.png",
            z=-1000,
            parallax=0.2,
            repeat_x=True,
            repeat_y=False,
        ),
    ]
    draw_background_layers(
        layers,
        camera_x=100.0,
        camera_y=0.0,
        viewport_w=320.0,
        viewport_h=180.0,
        zoom=1.0,
        draw_texture=draw_stub,
        get_texture=lambda _path: DummyTexture(),
    )

    assert len(calls) >= 2
