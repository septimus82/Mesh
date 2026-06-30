"""Pure math tests for parallax layer anchoring."""

from __future__ import annotations

import pytest

from engine.background_layers import (
    BackgroundLayer,
    clamp_camera_to_world_bounds,
    compute_background_world_center,
    compute_texture_world_bounds,
    draw_background_layers,
    parse_background_layers,
    resolve_background_layer_anchor,
    viewport_is_inside_texture,
)


class _FakeTexture:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height


@pytest.mark.fast
def test_world_rect_anchor_spans_zero_to_world_size() -> None:
    world_w = 1402.0
    world_h = 1122.0
    layer = BackgroundLayer(
        id="map",
        path="map.png",
        z=0,
        parallax=1.0,
        anchor="world_rect",
    )
    anchor_x, anchor_y = resolve_background_layer_anchor(
        layer, texture_width=world_w, texture_height=world_h
    )
    assert anchor_x == world_w / 2.0
    assert anchor_y == world_h / 2.0

    center_x, center_y = compute_background_world_center(
        camera_x=701.0,
        camera_y=561.0,
        parallax=1.0,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )
    left, bottom, right, top = compute_texture_world_bounds(
        center_x=center_x,
        center_y=center_y,
        width=world_w,
        height=world_h,
    )
    assert (left, bottom, right, top) == (0.0, 0.0, world_w, world_h)


@pytest.mark.fast
def test_parse_background_layers_reads_anchor_fields() -> None:
    payload = {
        "background_layers": [
            {
                "id": "map",
                "path": "assets/map.png",
                "z": 0,
                "anchor": "world_rect",
            },
            {
                "id": "sky",
                "path": "assets/sky.png",
                "z": -10,
                "anchor_x": 12.5,
                "anchor_y": -3.0,
            },
        ]
    }
    layers = parse_background_layers(payload)
    assert len(layers) == 2
    by_id = {layer.id: layer for layer in layers}
    assert by_id["map"].anchor == "world_rect"
    assert by_id["sky"].anchor_x == 12.5
    assert by_id["sky"].anchor_y == -3.0
    assert by_id["sky"].anchor is None


@pytest.mark.fast
def test_back_compat_center_anchor_unchanged_without_anchor_fields() -> None:
    layer = BackgroundLayer(id="bg", path="bg.png", z=0, parallax=1.0)
    anchor_x, anchor_y = resolve_background_layer_anchor(
        layer, texture_width=1402.0, texture_height=1122.0
    )
    assert (anchor_x, anchor_y) == (0.0, 0.0)
    assert compute_background_world_center(
        camera_x=100.0,
        camera_y=50.0,
        parallax=1.0,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    ) == (0.0, 0.0)

    recorded: list[tuple[float, float, float, float]] = []

    def recorder(cx: float, cy: float, w: float, h: float, tex: _FakeTexture) -> None:
        recorded.append((cx, cy, w, h))

    draw_background_layers(
        [layer],
        camera_x=100.0,
        camera_y=50.0,
        viewport_w=800.0,
        viewport_h=600.0,
        coordinate_space="world",
        draw_texture=recorder,
        get_texture=lambda _path: _FakeTexture(200, 100),
    )
    assert recorded == [(0.0, 0.0, 200.0, 100.0)]


@pytest.mark.fast
def test_world_rect_layer_draw_center_matches_texture_half_dims() -> None:
    layer = BackgroundLayer(
        id="map",
        path="map.png",
        z=0,
        parallax=1.0,
        anchor="world_rect",
    )
    recorded: list[tuple[float, float]] = []

    def recorder(cx: float, cy: float, w: float, h: float, tex: _FakeTexture) -> None:
        recorded.append((cx, cy))

    draw_background_layers(
        [layer],
        camera_x=701.0,
        camera_y=561.0,
        viewport_w=1280.0,
        viewport_h=720.0,
        coordinate_space="world",
        draw_texture=recorder,
        get_texture=lambda _path: _FakeTexture(1402, 1122),
    )
    assert recorded == [(701.0, 561.0)]


@pytest.mark.fast
def test_camera_clamps_keep_viewport_inside_world_rect_map() -> None:
    world_w = 1402.0
    world_h = 1122.0
    viewport_w = 1280.0
    viewport_h = 720.0
    layer = BackgroundLayer(
        id="map",
        path="map.png",
        z=0,
        parallax=1.0,
        anchor="world_rect",
    )

    player_x = world_w / 2.0
    player_y = world_h / 2.0
    camera_x, camera_y = clamp_camera_to_world_bounds(
        player_x,
        player_y,
        world_width=world_w,
        world_height=world_h,
        viewport_width=viewport_w,
        viewport_height=viewport_h,
    )
    assert viewport_is_inside_texture(
        camera_x=camera_x,
        camera_y=camera_y,
        viewport_width=viewport_w,
        viewport_height=viewport_h,
        texture_width=world_w,
        texture_height=world_h,
        layer=layer,
    )

    min_x, min_y = clamp_camera_to_world_bounds(
        0.0,
        0.0,
        world_width=world_w,
        world_height=world_h,
        viewport_width=viewport_w,
        viewport_height=viewport_h,
    )
    max_x, max_y = clamp_camera_to_world_bounds(
        world_w,
        world_h,
        world_width=world_w,
        world_height=world_h,
        viewport_width=viewport_w,
        viewport_height=viewport_h,
    )

    for camera in ((min_x, min_y), (max_x, max_y), (camera_x, camera_y)):
        assert viewport_is_inside_texture(
            camera_x=camera[0],
            camera_y=camera[1],
            viewport_width=viewport_w,
            viewport_height=viewport_h,
            texture_width=world_w,
            texture_height=world_h,
            layer=layer,
        )
