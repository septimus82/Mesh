"""Contract tests for sprite_outline_model."""

from __future__ import annotations

from engine.editor.sprite_outline_model import (
    OutlineSettings,
    compute_outline_alpha,
    compute_outline_offsets,
    compute_sprite_outline_draw_calls,
    get_outline_overrides,
)


def test_offsets_stable() -> None:
    assert compute_outline_offsets(0) == []
    assert compute_outline_offsets(1) == [
        (-1, 0),
        (1, 0),
        (0, -1),
        (0, 1),
        (-1, -1),
        (-1, 1),
        (1, -1),
        (1, 1),
    ]


def test_alpha_clamped_and_deterministic() -> None:
    settings = OutlineSettings(enabled=True, color_rgba=(0, 0, 0, 255), strength=2.0, radius_px=1, near_factor=1.0)
    alpha = compute_outline_alpha(100, 1000.0, settings)
    assert alpha == 255

    alpha2 = compute_outline_alpha(100, 1000.0, settings)
    assert alpha2 == alpha


def test_depth_alpha_monotonic() -> None:
    settings = OutlineSettings(enabled=True, color_rgba=(0, 0, 0, 120), strength=1.0, radius_px=1, near_factor=1.0)
    far = compute_outline_alpha(-5, -50.0, settings)
    near = compute_outline_alpha(5, 50.0, settings)
    assert near >= far


def test_overrides_deterministic() -> None:
    overrides = get_outline_overrides(
        {
            "outline_enabled": True,
            "outline_color_rgba": [10, 20, 30, 40],
            "outline_strength": 0.75,
            "outline_radius_px": 2,
        }
    )
    assert overrides == {
        "enabled": True,
        "color_rgba": (10, 20, 30, 40),
        "strength": 0.75,
        "radius_px": 2,
    }


def test_draw_call_order_stable() -> None:
    settings = OutlineSettings(enabled=True, color_rgba=(10, 20, 30, 80), strength=1.0, radius_px=1, near_factor=1.0)
    calls = compute_sprite_outline_draw_calls(100.0, 200.0, 0, 0.0, settings)
    assert [(call.x, call.y) for call in calls] == [
        (99.0, 200.0),
        (101.0, 200.0),
        (100.0, 199.0),
        (100.0, 201.0),
        (99.0, 199.0),
        (99.0, 201.0),
        (101.0, 199.0),
        (101.0, 201.0),
    ]
