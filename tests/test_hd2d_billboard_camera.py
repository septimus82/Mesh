"""#485: an HD-2D billboard stands 1 / cos(pitch) tall for the camera drawing the frame (handed to it as ``stretch``),
never for the renderer's own (game) camera; the depth-of-field focus measures the character the same way. No GL:
the renderer's methods on stand-ins (tests/test_hd2d_billboard_camera_gpu.py checks the pictures)."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from engine.hd2d import dof as d
from engine.hd2d.renderer import PIXELS_PER_METRE, Camera, Hd2dRenderer


def _stretch(pitch: float) -> float:
    return 1.0 / max(0.5, math.cos(math.radians(pitch)))


def _renderer(game_pitch: float) -> SimpleNamespace:
    return SimpleNamespace(camera=Camera(game_pitch, 12.0, 53.5, False), _sprite_texture=lambda texture: texture,
                           elevation_of=Hd2dRenderer.elevation_of, _quad=Hd2dRenderer._quad)


def _sprite(texture: str, height: float, elevation: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(texture=texture, center_x=320.0, bottom=96.0, width=32.0, height=height, scale_x=1.0,
                           mesh_entity_data={"elevation": elevation})


@pytest.mark.parametrize("drawing_pitch", [15.0, 30.0, 40.0, 55.0, 85.0])
def test_a_billboard_is_as_tall_as_the_drawing_camera_s_pitch_needs_whatever_the_game_camera(drawing_pitch: float) -> None:
    sprites = [_sprite("door", 96.0), _sprite("elder", 48.0, elevation=32.0)]
    for game_pitch in (30.0, 55.0, 89.0):  # (the room's pitches, and one far off: it must not matter)
        verts, idx, ranges = Hd2dRenderer._sprite_quads(_renderer(game_pitch), sprites, False,
                                                        stretch=_stretch(drawing_pitch))
        heights = []
        for _texture, first, count in ranges:
            for q in range(first, first + count, 6):
                i = idx[q] * 5  # (its first corner, at its feet; its third, at its head)
                heights.append((verts[i + 2], verts[i + 12] - verts[i + 2]))
        assert heights == [pytest.approx((0.0, 96.0 / PIXELS_PER_METRE * _stretch(drawing_pitch))),
                           pytest.approx((32.0 / PIXELS_PER_METRE, 48.0 / PIXELS_PER_METRE * _stretch(drawing_pitch)))]


def test_the_stretch_is_the_drawing_camera_s_not_a_default() -> None:
    with pytest.raises(TypeError):  # (no fallback to the renderer's own camera: the caller says which camera draws)
        Hd2dRenderer._sprite_quads(_renderer(30.0), [_sprite("elder", 48.0)], False)


def test_the_depth_of_field_focus_measures_the_character_for_the_camera_it_is_given() -> None:
    sprite = SimpleNamespace(mesh_tag="player", center_x=320.0, bottom=96.0, height=48.0, width=32.0)
    cam = Camera(55.0, 12.0, 53.5, False)
    cam.target = (10.0, 1.0, 0.8)
    fake = SimpleNamespace(camera=Camera(30.0, 12.0, 53.5, False), followed=lambda: sprite, elevation_of=lambda s: 0.0)
    focus, need = Hd2dRenderer.dof_focus(fake, cam, True)
    h = 1.5 * _stretch(55.0)
    assert focus == pytest.approx(d.view_depth(cam.eye(), cam.target, (10.0, 3.0, h / 2)))
    assert need == pytest.approx(d.character_band(h, 55.0))
