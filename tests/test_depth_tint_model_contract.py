"""Contract tests for depth_tint_model.py.

Tests verify:
- Depth factor monotonicity and clamping
- Color lerping correctness
- Tint computation determinism
- Near/far endpoint behavior
- Override handling
"""

from __future__ import annotations

import pytest

from engine.depth_tint_model import (
    DepthTintSettings,
    DEFAULT_DEPTH_TINT_SETTINGS,
    compute_depth_factor,
    lerp_color,
    compute_tint_rgba,
    apply_tint_to_color,
    parse_depth_tint_settings,
    should_apply_depth_tint,
    get_entity_tint_strength_override,
    compute_sprite_tint,
    apply_tint_to_sprite_color,
)
from tests._typing import as_any


class TestDepthTintSettingsDataclass:
    """Tests for DepthTintSettings dataclass."""

    def test_default_settings_disabled(self) -> None:
        """Default settings have enabled=False."""
        assert DEFAULT_DEPTH_TINT_SETTINGS.enabled is False

    def test_settings_to_dict(self) -> None:
        """to_dict() returns serializable representation."""
        settings = DepthTintSettings(
            enabled=True,
            near_color=(255, 255, 255, 255),
            far_color=(100, 100, 120, 255),
            strength=0.5,
        )
        d = settings.to_dict()
        assert d["enabled"] is True
        assert d["near_color"] == [255, 255, 255, 255]
        assert d["far_color"] == [100, 100, 120, 255]
        assert d["strength"] == 0.5

    def test_settings_frozen(self) -> None:
        """Settings dataclass is frozen."""
        settings = DepthTintSettings()
        with pytest.raises(AttributeError):
            as_any(settings).enabled = True


class TestComputeDepthFactor:
    """Tests for compute_depth_factor function."""

    def test_zero_depth_returns_mid_factor(self) -> None:
        """render_layer=0, depth_z=0 returns ~0.5 (middle of range)."""
        factor = compute_depth_factor(0, 0.0)
        assert 0.4 <= factor <= 0.6

    def test_high_render_layer_near(self) -> None:
        """Higher render_layer = nearer = lower factor."""
        factor = compute_depth_factor(10, 0.0, layer_range=(-10, 10))
        assert factor < 0.1  # Near zero (near)

    def test_low_render_layer_far(self) -> None:
        """Lower render_layer = farther = higher factor."""
        factor = compute_depth_factor(-10, 0.0, layer_range=(-10, 10))
        assert factor > 0.9  # Near one (far)

    def test_monotonicity_by_render_layer(self) -> None:
        """Depth factor increases as render_layer decreases."""
        factors = [
            compute_depth_factor(rl, 0.0)
            for rl in [10, 5, 0, -5, -10]
        ]
        for i in range(len(factors) - 1):
            assert factors[i] < factors[i + 1], f"Not monotonic at index {i}"

    def test_explicit_z_mode_uses_depth_z(self) -> None:
        """explicit_z mode weights depth_z more heavily."""
        # Same render_layer, different depth_z
        near = compute_depth_factor(0, 50.0, sort_mode="explicit_z")
        far = compute_depth_factor(0, -50.0, sort_mode="explicit_z")
        assert near < far  # Higher depth_z = nearer = lower factor

    def test_monotonicity_by_depth_z_explicit(self) -> None:
        """In explicit_z mode, factor increases as depth_z decreases."""
        factors = [
            compute_depth_factor(0, dz, sort_mode="explicit_z")
            for dz in [100.0, 50.0, 0.0, -50.0, -100.0]
        ]
        for i in range(len(factors) - 1):
            assert factors[i] < factors[i + 1], f"Not monotonic at index {i}"

    def test_clamped_to_zero_one(self) -> None:
        """Factor is always clamped to [0, 1]."""
        # Far beyond range
        far = compute_depth_factor(-1000, -10000.0)
        assert 0.0 <= far <= 1.0

        near = compute_depth_factor(1000, 10000.0)
        assert 0.0 <= near <= 1.0

    def test_deterministic(self) -> None:
        """Same inputs always produce same output."""
        for _ in range(10):
            f = compute_depth_factor(5, 25.5, sort_mode="explicit_z")
            assert f == compute_depth_factor(5, 25.5, sort_mode="explicit_z")


class TestLerpColor:
    """Tests for lerp_color function."""

    def test_t_zero_returns_c0(self) -> None:
        """t=0 returns first color."""
        result = lerp_color((255, 0, 0, 255), (0, 255, 0, 255), 0.0)
        assert result == (255, 0, 0, 255)

    def test_t_one_returns_c1(self) -> None:
        """t=1 returns second color."""
        result = lerp_color((255, 0, 0, 255), (0, 255, 0, 255), 1.0)
        assert result == (0, 255, 0, 255)

    def test_t_half_returns_midpoint(self) -> None:
        """t=0.5 returns midpoint."""
        result = lerp_color((0, 0, 0, 0), (255, 255, 255, 255), 0.5)
        assert result == (128, 128, 128, 128)  # Rounded

    def test_handles_rgb_input(self) -> None:
        """Works with RGB (no alpha) input."""
        result = lerp_color(as_any((255, 0, 0)), as_any((0, 255, 0)), 0.5)
        assert result == (128, 128, 0, 255)  # Alpha defaults to 255

    def test_clamps_t(self) -> None:
        """t is clamped to [0, 1]."""
        below = lerp_color((100, 100, 100, 100), (200, 200, 200, 200), -0.5)
        assert below == (100, 100, 100, 100)  # Same as t=0

        above = lerp_color((100, 100, 100, 100), (200, 200, 200, 200), 1.5)
        assert above == (200, 200, 200, 200)  # Same as t=1


class TestComputeTintRgba:
    """Tests for compute_tint_rgba function."""

    def test_disabled_returns_neutral(self) -> None:
        """Disabled settings return neutral white."""
        settings = DepthTintSettings(enabled=False)
        tint = compute_tint_rgba(5, 10.0, settings)
        assert tint == (255, 255, 255, 255)

    def test_none_settings_returns_neutral(self) -> None:
        """None settings return neutral (default is disabled)."""
        tint = compute_tint_rgba(5, 10.0, None)
        assert tint == (255, 255, 255, 255)

    def test_enabled_near_position(self) -> None:
        """Near position gets near_color influence."""
        settings = DepthTintSettings(
            enabled=True,
            near_color=(255, 255, 255, 255),
            far_color=(100, 100, 100, 255),
            strength=1.0,  # Full effect
            layer_range=(-10, 10),
        )
        # render_layer=10 is maximum (near)
        tint = compute_tint_rgba(10, 0.0, settings)
        # Should be close to near_color
        assert tint[0] >= 250  # R near 255

    def test_enabled_far_position(self) -> None:
        """Far position gets far_color influence."""
        settings = DepthTintSettings(
            enabled=True,
            near_color=(255, 255, 255, 255),
            far_color=(100, 100, 100, 255),
            strength=1.0,  # Full effect
            layer_range=(-10, 10),
        )
        # render_layer=-10 is minimum (far)
        tint = compute_tint_rgba(-10, 0.0, settings)
        # Should be close to far_color
        assert tint[0] <= 110  # R near 100

    def test_strength_zero_returns_neutral(self) -> None:
        """strength=0 returns neutral regardless of depth."""
        settings = DepthTintSettings(
            enabled=True,
            far_color=(0, 0, 0, 255),
            strength=0.0,
        )
        tint = compute_tint_rgba(-10, -100.0, settings)
        assert tint == (255, 255, 255, 255)

    def test_strength_affects_intensity(self) -> None:
        """Higher strength = more tint effect."""
        far_layer = -10
        weak = DepthTintSettings(enabled=True, strength=0.1, far_color=(100, 100, 100, 255))
        strong = DepthTintSettings(enabled=True, strength=0.9, far_color=(100, 100, 100, 255))

        weak_tint = compute_tint_rgba(far_layer, 0.0, weak)
        strong_tint = compute_tint_rgba(far_layer, 0.0, strong)

        # Strong tint should be darker (lower values)
        assert strong_tint[0] < weak_tint[0]

    def test_deterministic(self) -> None:
        """Same inputs always produce same output."""
        settings = DepthTintSettings(enabled=True, strength=0.5)
        for _ in range(10):
            t1 = compute_tint_rgba(3, 15.0, settings, sort_mode="explicit_z")
            t2 = compute_tint_rgba(3, 15.0, settings, sort_mode="explicit_z")
            assert t1 == t2


class TestApplyTintToColor:
    """Tests for apply_tint_to_color function."""

    def test_neutral_tint_preserves_color(self) -> None:
        """Neutral tint (255,255,255,255) preserves original."""
        base = (200, 150, 100, 255)
        result = apply_tint_to_color(base, (255, 255, 255, 255))
        assert result == base

    def test_black_tint_produces_black(self) -> None:
        """Black tint (0,0,0,255) produces black."""
        base = (255, 255, 255, 255)
        result = apply_tint_to_color(base, (0, 0, 0, 255))
        assert result == (0, 0, 0, 255)

    def test_multiplicative_blend(self) -> None:
        """Tint is applied multiplicatively."""
        base = (200, 200, 200, 255)
        # 50% tint (128 = ~50% of 255)
        tint = (128, 128, 128, 255)
        result = apply_tint_to_color(base, tint)
        # 200 * 128 / 255 ≈ 100
        assert 95 <= result[0] <= 105

    def test_handles_rgb_base(self) -> None:
        """Works with RGB base color."""
        base = as_any((200, 150, 100))
        result = apply_tint_to_color(base, (255, 255, 255, 255))
        assert result == (200, 150, 100, 255)

    def test_clamped_to_valid_range(self) -> None:
        """Result is always clamped to [0, 255]."""
        result = apply_tint_to_color((255, 255, 255, 255), (255, 255, 255, 255))
        assert all(0 <= c <= 255 for c in result)


class TestParseDepthTintSettings:
    """Tests for parse_depth_tint_settings function."""

    def test_none_returns_default(self) -> None:
        """None input returns default settings."""
        settings = parse_depth_tint_settings(None)
        assert settings.enabled is False

    def test_empty_dict_returns_default(self) -> None:
        """Empty dict returns default settings."""
        settings = parse_depth_tint_settings({})
        assert settings.enabled is False

    def test_enabled_parsed(self) -> None:
        """depth_tint_enabled is parsed."""
        settings = parse_depth_tint_settings({"depth_tint_enabled": True})
        assert settings.enabled is True

    def test_colors_parsed(self) -> None:
        """near_color and far_color are parsed."""
        settings = parse_depth_tint_settings({
            "depth_tint_enabled": True,
            "depth_tint_near_color": [255, 200, 150, 200],
            "depth_tint_far_color": [50, 50, 80],
        })
        assert settings.near_color == (255, 200, 150, 200)
        assert settings.far_color == (50, 50, 80, 255)  # Alpha defaults to 255

    def test_strength_parsed(self) -> None:
        """depth_tint_strength is parsed and clamped."""
        settings = parse_depth_tint_settings({
            "depth_tint_enabled": True,
            "depth_tint_strength": 0.75,
        })
        assert settings.strength == 0.75

        # Clamped
        over = parse_depth_tint_settings({
            "depth_tint_enabled": True,
            "depth_tint_strength": 2.0,
        })
        assert over.strength == 1.0

    def test_invalid_values_use_defaults(self) -> None:
        """Invalid values fall back to defaults."""
        settings = parse_depth_tint_settings({
            "depth_tint_enabled": True,
            "depth_tint_strength": "not a number",
            "depth_tint_near_color": "invalid",
        })
        assert settings.strength == DEFAULT_DEPTH_TINT_SETTINGS.strength
        assert settings.near_color == DEFAULT_DEPTH_TINT_SETTINGS.near_color


class TestShouldApplyDepthTint:
    """Tests for should_apply_depth_tint function."""

    def test_none_returns_default(self) -> None:
        """None entity returns default."""
        assert should_apply_depth_tint(None) is True
        assert should_apply_depth_tint(None, default_enabled=False) is False

    def test_empty_dict_returns_default(self) -> None:
        """Empty dict returns default."""
        assert should_apply_depth_tint({}) is True

    def test_explicit_enabled(self) -> None:
        """Explicit depth_tint_enabled overrides default."""
        assert should_apply_depth_tint({"depth_tint_enabled": False}) is False
        assert should_apply_depth_tint({"depth_tint_enabled": True}) is True


class TestGetEntityTintStrengthOverride:
    """Tests for get_entity_tint_strength_override function."""

    def test_none_returns_none(self) -> None:
        """None entity returns None."""
        assert get_entity_tint_strength_override(None) is None

    def test_missing_returns_none(self) -> None:
        """Missing field returns None."""
        assert get_entity_tint_strength_override({}) is None

    def test_valid_value_returned(self) -> None:
        """Valid value is returned."""
        assert get_entity_tint_strength_override({"depth_tint_strength": 0.5}) == 0.5

    def test_clamped_to_range(self) -> None:
        """Value is clamped to [0, 1]."""
        assert get_entity_tint_strength_override({"depth_tint_strength": -0.5}) == 0.0
        assert get_entity_tint_strength_override({"depth_tint_strength": 1.5}) == 1.0

    def test_invalid_returns_none(self) -> None:
        """Invalid value returns None."""
        assert get_entity_tint_strength_override({"depth_tint_strength": "bad"}) is None


class TestComputeSpriteTint:
    """Tests for compute_sprite_tint function."""

    def test_disabled_settings_returns_none(self) -> None:
        """Disabled settings return None."""
        settings = DepthTintSettings(enabled=False)

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {}

        result = compute_sprite_tint(FakeSprite(), settings)
        assert result is None

    def test_entity_disabled_returns_none(self) -> None:
        """Entity with depth_tint_enabled=False returns None."""
        settings = DepthTintSettings(enabled=True)

        class FakeSprite:
            mesh_entity_data = {"depth_tint_enabled": False}

        result = compute_sprite_tint(FakeSprite(), settings)
        assert result is None

    def test_returns_tint_when_enabled(self) -> None:
        """Returns tint color when enabled."""
        settings = DepthTintSettings(enabled=True, strength=0.5)

        class FakeSprite:
            mesh_entity_data = {"render_layer": 0}

        result = compute_sprite_tint(FakeSprite(), settings)
        assert result is not None
        assert len(result) == 4

    def test_respects_entity_strength_override(self) -> None:
        """Entity strength override is applied."""
        settings = DepthTintSettings(
            enabled=True,
            strength=0.9,  # Scene strength
            far_color=(100, 100, 100, 255),
        )

        class WeakSprite:
            mesh_entity_data = {"render_layer": -10, "depth_tint_strength": 0.1}

        class StrongSprite:
            mesh_entity_data = {"render_layer": -10}  # Uses scene strength

        weak_tint = compute_sprite_tint(WeakSprite(), settings)
        strong_tint = compute_sprite_tint(StrongSprite(), settings)

        assert weak_tint is not None
        assert strong_tint is not None
        # Weak tint should be brighter (closer to neutral)
        assert weak_tint[0] > strong_tint[0]


class TestApplyTintToSpriteColor:
    """Tests for apply_tint_to_sprite_color function."""

    def test_none_color_uses_white(self) -> None:
        """None sprite color defaults to white."""
        result = apply_tint_to_sprite_color(None, (128, 128, 128, 255))
        assert result == (128, 128, 128, 255)

    def test_valid_color_tinted(self) -> None:
        """Valid sprite color is tinted."""
        result = apply_tint_to_sprite_color((200, 200, 200, 255), (255, 255, 255, 255))
        assert result == (200, 200, 200, 255)


class TestDeterminism:
    """Tests verifying deterministic behavior."""

    def test_full_pipeline_deterministic(self) -> None:
        """Full tint computation is deterministic."""
        settings = DepthTintSettings(
            enabled=True,
            strength=0.5,
            far_color=(100, 100, 120, 255),
        )

        class FakeSprite:
            mesh_entity_data = {"render_layer": 3, "depth_z": 25.0}

        for _ in range(10):
            t1 = compute_sprite_tint(FakeSprite(), settings, sort_mode="explicit_z")
            t2 = compute_sprite_tint(FakeSprite(), settings, sort_mode="explicit_z")
            assert t1 == t2

    def test_depth_tint_monotonic_across_layers(self) -> None:
        """Tint gets darker (lower values) for farther layers."""
        settings = DepthTintSettings(
            enabled=True,
            strength=1.0,
            near_color=(255, 255, 255, 255),
            far_color=(100, 100, 100, 255),
            layer_range=(-10, 10),
        )

        tints = [
            compute_tint_rgba(rl, 0.0, settings)
            for rl in [10, 5, 0, -5, -10]
        ]

        # Red channel should decrease (get darker) as we go farther
        for i in range(len(tints) - 1):
            assert tints[i][0] >= tints[i + 1][0], f"Not monotonic at index {i}"
