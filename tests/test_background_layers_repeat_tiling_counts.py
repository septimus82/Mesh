from __future__ import annotations

from dataclasses import dataclass

from engine.background_layers import BackgroundLayer, draw_background_layers


@dataclass(slots=True)
class DummyTexture:
    width: int = 64
    height: int = 32


def test_background_layers_repeat_x_draw_count_covers_viewport():
    calls: list[tuple[float, float, float, float]] = []

    def draw_stub(cx: float, cy: float, w: float, h: float, _tex: DummyTexture) -> None:
        calls.append((cx, cy, w, h))

    layer = BackgroundLayer(
        id="Sky",
        path="assets/bg/sky.png",
        z=-1000,
        parallax=0.0,
        repeat_x=True,
        repeat_y=False,
    )
    viewport_w = 200.0
    viewport_h = 100.0
    draw_background_layers(
        [layer],
        camera_x=0.0,
        camera_y=0.0,
        viewport_w=viewport_w,
        viewport_h=viewport_h,
        zoom=1.0,
        draw_texture=draw_stub,
        get_texture=lambda _path: DummyTexture(),
    )

    tile_w = 64.0
    base_x = viewport_w / 2.0
    left_needed = -tile_w / 2.0
    right_needed = viewport_w + tile_w / 2.0
    n_min = int((left_needed - base_x) // tile_w) - 1
    n_max = int((right_needed - base_x) // tile_w) + 1
    expected_count = n_max - n_min + 1

    assert len(calls) == expected_count
    centers_x = [cx for (cx, _cy, _w, _h) in calls]
    assert min(centers_x) <= left_needed
    assert max(centers_x) >= right_needed

