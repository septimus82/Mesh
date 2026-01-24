from __future__ import annotations

import math

import pytest

from engine.lighting.flicker import FlickerNoise

pytestmark = pytest.mark.fast


def test_light_flicker_noise_deterministic() -> None:
    noise = FlickerNoise(42)
    a = noise.sample(0.125)
    b = noise.sample(0.125)
    assert a == pytest.approx(b)

    noise_b = FlickerNoise(43)
    c = noise_b.sample(0.125)
    assert c != pytest.approx(a)

    assert -1.0 <= a <= 1.0
    assert math.isfinite(a)
