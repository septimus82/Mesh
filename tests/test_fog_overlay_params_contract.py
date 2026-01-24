from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.ui_overlays.fog_overlay import compute_fog_rgba, resolve_fog_rgba

pytestmark = pytest.mark.fast


def test_fog_disabled_noop() -> None:
    rgba = compute_fog_rgba(
        enabled=False,
        fog_rgba=(255, 255, 255, 200),
        density=1.0,
        noise_amount=0.5,
        noise_speed=1.0,
        time_s=1.0,
        seed=123,
    )
    assert rgba is None


def test_fog_alpha_within_bounds() -> None:
    rgba = compute_fog_rgba(
        enabled=True,
        fog_rgba=(10, 20, 30, 200),
        density=0.5,
        noise_amount=0.25,
        noise_speed=0.5,
        time_s=2.0,
        seed=4,
    )
    assert rgba is not None
    assert 0 <= rgba[3] <= 255
    assert rgba[:3] == (10, 20, 30)


def test_fog_noise_deterministic() -> None:
    rgba_a = compute_fog_rgba(
        enabled=True,
        fog_rgba=(255, 255, 255, 200),
        density=0.7,
        noise_amount=0.4,
        noise_speed=1.25,
        time_s=3.5,
        seed=42,
    )
    rgba_b = compute_fog_rgba(
        enabled=True,
        fog_rgba=(255, 255, 255, 200),
        density=0.7,
        noise_amount=0.4,
        noise_speed=1.25,
        time_s=3.5,
        seed=42,
    )
    assert rgba_a == rgba_b


def test_fog_ambient_tint_used_when_unset() -> None:
    cfg = SimpleNamespace(fog_rgba=(255, 255, 255, 0), ambient_light_rgba=(120, 160, 255, 255))
    scene_settings = {"ambient_light_rgba": [100, 120, 200, 255]}
    resolved = resolve_fog_rgba(cfg, scene_settings, scene_settings["ambient_light_rgba"])
    assert resolved[:3] == (100, 120, 200)
    rgba = compute_fog_rgba(
        enabled=True,
        fog_rgba=resolved,
        density=0.4,
        noise_amount=0.0,
        noise_speed=0.0,
        time_s=0.0,
        seed=0,
    )
    assert rgba is not None
    assert rgba[3] > 0


def test_fog_explicit_rgba_overrides_ambient() -> None:
    cfg = SimpleNamespace(fog_rgba=(255, 255, 255, 0), ambient_light_rgba=(10, 20, 30, 255))
    scene_settings = {"fog_rgba": [5, 6, 7, 128], "ambient_light_rgba": [200, 200, 200, 255]}
    resolved = resolve_fog_rgba(cfg, scene_settings, scene_settings["ambient_light_rgba"])
    assert resolved[:3] == (5, 6, 7)
