from __future__ import annotations

import pytest

from engine.lighting.light_shafts import build_shafts_params, compute_shafts_alpha

pytestmark = pytest.mark.fast


def test_shafts_disabled_returns_none() -> None:
    params = build_shafts_params(
        (10.0, 20.0),
        (255, 255, 255, 255),
        100.0,
        {"shafts_enabled": False},
        0.5,
    )
    assert params is None


def test_shafts_alpha_deterministic_and_bounded() -> None:
    alpha_a = compute_shafts_alpha(0.35, 1.25, 0.08, 0.15)
    alpha_b = compute_shafts_alpha(0.35, 1.25, 0.08, 0.15)
    assert 0.0 <= alpha_a <= 1.0
    assert alpha_a == alpha_b


def test_shafts_color_fallback_to_white() -> None:
    params = build_shafts_params(
        (0.0, 0.0),
        None,
        120.0,
        {"shafts_enabled": True},
        0.0,
    )
    assert params is not None
    assert params["color_rgba"][:3] == (255, 255, 255)


def test_shafts_color_uses_input_tint() -> None:
    params = build_shafts_params(
        (0.0, 0.0),
        (10, 20, 30, 255),
        120.0,
        {"shafts_enabled": True, "shafts_alpha": 0.5},
        0.0,
    )
    assert params is not None
    assert params["color_rgba"][:3] == (10, 20, 30)
