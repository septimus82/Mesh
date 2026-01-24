from __future__ import annotations

import pytest

from engine.lighting.flicker import FlickerNoise, apply_light_flicker

pytestmark = pytest.mark.fast


def test_light_flicker_disabled_keeps_values() -> None:
    base_radius = 100.0
    base_color = (120, 130, 140, 200)
    noise = FlickerNoise(7)

    radius, color = apply_light_flicker(
        base_radius=base_radius,
        base_color=base_color,
        noise=noise,
        time_s=0.5,
        speed=1.0,
        amount=0.0,
        radius_px=None,
        intensity=None,
    )

    assert radius == pytest.approx(base_radius)
    assert color == base_color


def test_light_flicker_enabled_adjusts_values() -> None:
    base_radius = 100.0
    base_color = (100, 120, 140, 200)
    noise = FlickerNoise(5)

    sample = noise.sample(0.5)
    radius, color = apply_light_flicker(
        base_radius=base_radius,
        base_color=base_color,
        noise=noise,
        time_s=0.5,
        speed=1.0,
        amount=0.2,
        radius_px=None,
        intensity=None,
    )

    expected_radius = base_radius * (1.0 + 0.2 * sample)
    expected_scale = max(0.0, 1.0 + 0.2 * sample)
    expected_color = tuple(int(round(channel * expected_scale)) for channel in base_color)

    assert radius == pytest.approx(expected_radius)
    assert color == expected_color
