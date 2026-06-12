"""Contract tests for sprite_shadow_model.py.

Tests verify:
- Deterministic shadow parameter computation
- Depth-based scaling behavior
- Alpha clamping
- Override application
- Ellipse geometry
- Contact shadow and AO shadow layers
"""

from __future__ import annotations

import pytest

from engine.sprite_shadow_model import (
    DEFAULT_AO_SCALE,
    DEFAULT_CONTACT_SCALE,
    DEFAULT_SHADOW_HEIGHT,
    DEFAULT_SHADOW_WIDTH,
    MAX_ALPHA,
    MAX_SCALE,
    MIN_ALPHA,
    MIN_SCALE,
    AoShadowParams,
    ContactShadowParams,
    MultiLayerShadow,
    ShadowEllipse,
    ShadowParams,
    compute_ao_shadow_ellipse,
    compute_ao_shadow_params,
    compute_contact_shadow_ellipse,
    compute_contact_shadow_params,
    compute_shadow_ellipse,
    compute_shadow_params,
    compute_shadow_params_with_overrides,
    compute_sprite_multi_shadow,
    compute_sprite_shadow,
    get_shadow_overrides,
    should_draw_ao_shadow,
    should_draw_contact_shadow,
    should_draw_shadow,
)
from tests._typing import as_any


class TestShadowParamsDataclass:
    """Tests for ShadowParams dataclass."""

    def test_shadowparams_to_dict(self) -> None:
        params = ShadowParams(scale=1.5, alpha=0.4, offset_y=-5.0)
        d = params.to_dict()
        assert d == {"scale": 1.5, "alpha": 0.4, "offset_y": -5.0}

    def test_shadowparams_frozen(self) -> None:
        params = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        with pytest.raises(AttributeError):
            as_any(params).scale = 2.0


class TestShadowEllipseDataclass:
    """Tests for ShadowEllipse dataclass."""

    def test_shadowellipse_to_tuple(self) -> None:
        ellipse = ShadowEllipse(cx=100.0, cy=50.0, width=24.0, height=8.0)
        assert ellipse.to_tuple() == (100.0, 50.0, 24.0, 8.0)

    def test_shadowellipse_frozen(self) -> None:
        ellipse = ShadowEllipse(cx=100.0, cy=50.0, width=24.0, height=8.0)
        with pytest.raises(AttributeError):
            as_any(ellipse).cx = 200.0


class TestComputeShadowParams:
    """Tests for compute_shadow_params function."""

    def test_default_params_at_zero_depth(self) -> None:
        """At render_layer=0, depth_z=0, should return base values."""
        params = compute_shadow_params(0, 0.0)
        assert params.scale == 1.0
        assert params.alpha == 0.35
        assert params.offset_y == -4.0

    def test_deterministic_same_inputs(self) -> None:
        """Same inputs always produce same outputs."""
        params1 = compute_shadow_params(5, 10.0)
        params2 = compute_shadow_params(5, 10.0)
        assert params1 == params2

    def test_higher_render_layer_larger_shadow(self) -> None:
        """Higher render_layer = nearer = larger shadow."""
        far = compute_shadow_params(-5, 0.0)
        near = compute_shadow_params(5, 0.0)
        assert near.scale > far.scale

    def test_higher_depth_z_larger_shadow(self) -> None:
        """Higher depth_z = nearer = larger shadow."""
        far = compute_shadow_params(0, -50.0)
        near = compute_shadow_params(0, 50.0)
        assert near.scale > far.scale

    def test_higher_render_layer_darker_shadow(self) -> None:
        """Higher render_layer = nearer = darker (higher alpha)."""
        far = compute_shadow_params(-5, 0.0)
        near = compute_shadow_params(5, 0.0)
        assert near.alpha > far.alpha

    def test_higher_depth_z_darker_shadow(self) -> None:
        """Higher depth_z = nearer = darker (higher alpha)."""
        far = compute_shadow_params(0, -50.0)
        near = compute_shadow_params(0, 50.0)
        assert near.alpha > far.alpha

    def test_scale_clamped_to_min(self) -> None:
        """Scale is clamped to MIN_SCALE."""
        params = compute_shadow_params(-100, -1000.0)
        assert params.scale >= MIN_SCALE

    def test_scale_clamped_to_max(self) -> None:
        """Scale is clamped to MAX_SCALE."""
        params = compute_shadow_params(100, 1000.0)
        assert params.scale <= MAX_SCALE

    def test_alpha_clamped_to_min(self) -> None:
        """Alpha is clamped to MIN_ALPHA."""
        params = compute_shadow_params(-100, -1000.0)
        assert params.alpha >= MIN_ALPHA

    def test_alpha_clamped_to_max(self) -> None:
        """Alpha is clamped to MAX_ALPHA."""
        params = compute_shadow_params(100, 1000.0)
        assert params.alpha <= MAX_ALPHA

    def test_custom_base_scale(self) -> None:
        """Custom base_scale is applied."""
        params = compute_shadow_params(0, 0.0, base_scale=2.0)
        assert params.scale == 2.0

    def test_custom_base_alpha(self) -> None:
        """Custom base_alpha is applied."""
        params = compute_shadow_params(0, 0.0, base_alpha=0.5)
        assert params.alpha == 0.5

    def test_custom_base_offset_y(self) -> None:
        """Custom base_offset_y is applied."""
        params = compute_shadow_params(0, 0.0, base_offset_y=-10.0)
        assert params.offset_y == -10.0

    def test_typical_hd2d_range(self) -> None:
        """Test typical HD-2D render_layer range [-10, 10]."""
        ground = compute_shadow_params(-10, 0.0)
        character = compute_shadow_params(0, 0.0)
        foreground = compute_shadow_params(10, 0.0)

        # Ground has smallest/lightest shadow
        assert ground.scale < character.scale < foreground.scale
        assert ground.alpha < character.alpha < foreground.alpha


class TestComputeShadowEllipse:
    """Tests for compute_shadow_ellipse function."""

    def test_ellipse_at_sprite_position(self) -> None:
        """Ellipse cx equals sprite x, cy offset by params.offset_y."""
        params = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        ellipse = compute_shadow_ellipse(100.0, 200.0, params)
        assert ellipse.cx == 100.0
        assert ellipse.cy == 200.0 + (-4.0)  # sprite_y + offset_y

    def test_ellipse_dimensions_scaled(self) -> None:
        """Ellipse dimensions are scaled by params.scale."""
        params = ShadowParams(scale=2.0, alpha=0.35, offset_y=-4.0)
        ellipse = compute_shadow_ellipse(0.0, 0.0, params)
        assert ellipse.width == DEFAULT_SHADOW_WIDTH * 2.0
        assert ellipse.height == DEFAULT_SHADOW_HEIGHT * 2.0

    def test_ellipse_custom_base_dimensions(self) -> None:
        """Custom base_width and base_height are respected."""
        params = ShadowParams(scale=1.0, alpha=0.35, offset_y=0.0)
        ellipse = compute_shadow_ellipse(
            0.0, 0.0, params, base_width=50.0, base_height=20.0
        )
        assert ellipse.width == 50.0
        assert ellipse.height == 20.0

    def test_ellipse_deterministic(self) -> None:
        """Same inputs always produce same ellipse."""
        params = ShadowParams(scale=1.5, alpha=0.4, offset_y=-6.0)
        e1 = compute_shadow_ellipse(123.456, 789.012, params)
        e2 = compute_shadow_ellipse(123.456, 789.012, params)
        assert e1 == e2


class TestShouldDrawShadow:
    """Tests for should_draw_shadow function."""

    def test_none_entity_returns_default_true(self) -> None:
        """None entity_data returns default_enabled."""
        assert should_draw_shadow(None) is True
        assert should_draw_shadow(None, default_enabled=False) is False

    def test_empty_dict_returns_default(self) -> None:
        """Empty dict returns default_enabled."""
        assert should_draw_shadow({}) is True
        assert should_draw_shadow({}, default_enabled=False) is False

    def test_shadow_enabled_true(self) -> None:
        """Explicit shadow_enabled=True returns True."""
        assert should_draw_shadow({"shadow_enabled": True}) is True

    def test_shadow_enabled_false(self) -> None:
        """Explicit shadow_enabled=False returns False."""
        assert should_draw_shadow({"shadow_enabled": False}) is False

    def test_shadow_enabled_truthy_values(self) -> None:
        """Truthy values for shadow_enabled return True."""
        assert should_draw_shadow({"shadow_enabled": 1}) is True
        assert should_draw_shadow({"shadow_enabled": "yes"}) is True

    def test_shadow_enabled_falsy_values(self) -> None:
        """Falsy values for shadow_enabled return False."""
        assert should_draw_shadow({"shadow_enabled": 0}) is False
        assert should_draw_shadow({"shadow_enabled": ""}) is False


class TestGetShadowOverrides:
    """Tests for get_shadow_overrides function."""

    def test_none_entity_returns_empty(self) -> None:
        """None entity_data returns empty dict."""
        assert get_shadow_overrides(None) == {}

    def test_empty_dict_returns_empty(self) -> None:
        """Empty dict returns empty overrides."""
        assert get_shadow_overrides({}) == {}

    def test_extracts_scale_mult(self) -> None:
        """shadow_scale extracted as scale_mult."""
        overrides = get_shadow_overrides({"shadow_scale": 1.5})
        assert overrides == {"scale_mult": 1.5}

    def test_extracts_alpha(self) -> None:
        """shadow_alpha extracted and clamped to 0..1."""
        assert get_shadow_overrides({"shadow_alpha": 0.5}) == {"alpha": 0.5}
        assert get_shadow_overrides({"shadow_alpha": -0.5}) == {"alpha": 0.0}
        assert get_shadow_overrides({"shadow_alpha": 1.5}) == {"alpha": 1.0}

    def test_extracts_offset_y(self) -> None:
        """shadow_offset_y extracted."""
        overrides = get_shadow_overrides({"shadow_offset_y": -10.0})
        assert overrides == {"offset_y": -10.0}

    def test_multiple_overrides(self) -> None:
        """Multiple overrides extracted together."""
        entity = {
            "shadow_scale": 2.0,
            "shadow_alpha": 0.6,
            "shadow_offset_y": -8.0,
        }
        overrides = get_shadow_overrides(entity)
        assert overrides == {
            "scale_mult": 2.0,
            "alpha": 0.6,
            "offset_y": -8.0,
        }

    def test_invalid_values_ignored(self) -> None:
        """Invalid values are ignored."""
        entity = {
            "shadow_scale": "not a number",
            "shadow_alpha": None,
            "shadow_offset_y": [],
        }
        assert get_shadow_overrides(entity) == {}


class TestComputeShadowParamsWithOverrides:
    """Tests for compute_shadow_params_with_overrides function."""

    def test_no_overrides_same_as_base(self) -> None:
        """Without overrides, same as compute_shadow_params."""
        base = compute_shadow_params(5, 10.0)
        with_overrides = compute_shadow_params_with_overrides(5, 10.0, {})
        assert base == with_overrides

    def test_scale_multiplier_applied(self) -> None:
        """shadow_scale multiplier is applied."""
        base = compute_shadow_params(0, 0.0)
        entity = {"shadow_scale": 2.0}
        with_overrides = compute_shadow_params_with_overrides(0, 0.0, entity)
        assert with_overrides.scale == base.scale * 2.0

    def test_alpha_override_replaces(self) -> None:
        """shadow_alpha replaces computed alpha."""
        entity = {"shadow_alpha": 0.8}
        with_overrides = compute_shadow_params_with_overrides(0, 0.0, entity)
        assert with_overrides.alpha == 0.8

    def test_offset_y_override_replaces(self) -> None:
        """shadow_offset_y replaces computed offset."""
        entity = {"shadow_offset_y": -15.0}
        with_overrides = compute_shadow_params_with_overrides(0, 0.0, entity)
        assert with_overrides.offset_y == -15.0

    def test_scale_still_clamped_with_override(self) -> None:
        """Scale is clamped even with multiplier override."""
        entity = {"shadow_scale": 100.0}
        with_overrides = compute_shadow_params_with_overrides(0, 0.0, entity)
        assert with_overrides.scale <= MAX_SCALE


class TestComputeSpriteShadow:
    """Tests for compute_sprite_shadow function."""

    def test_sprite_without_entity_data(self) -> None:
        """Sprite without mesh_entity_data gets default shadow."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0

        result = compute_sprite_shadow(FakeSprite())
        assert result is not None
        ellipse, alpha = result
        assert ellipse.cx == 100.0
        assert alpha == 0.35

    def test_sprite_with_shadow_disabled(self) -> None:
        """Sprite with shadow_enabled=False returns None."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"shadow_enabled": False}

        result = compute_sprite_shadow(FakeSprite())
        assert result is None

    def test_sprite_with_render_layer(self) -> None:
        """Sprite render_layer affects shadow params."""

        class FarSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"render_layer": -5}

        class NearSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"render_layer": 5}

        far_result = compute_sprite_shadow(FarSprite())
        near_result = compute_sprite_shadow(NearSprite())

        assert far_result is not None
        assert near_result is not None

        far_ellipse, far_alpha = far_result
        near_ellipse, near_alpha = near_result

        # Near sprite has larger, darker shadow
        assert near_ellipse.width > far_ellipse.width
        assert near_alpha > far_alpha

    def test_sprite_with_depth_z(self) -> None:
        """Sprite depth_z affects shadow params."""

        class FarSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"depth_z": -50.0}

        class NearSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"depth_z": 50.0}

        far_result = compute_sprite_shadow(FarSprite())
        near_result = compute_sprite_shadow(NearSprite())

        assert far_result is not None
        assert near_result is not None

        far_ellipse, _ = far_result
        near_ellipse, _ = near_result

        assert near_ellipse.width > far_ellipse.width

    def test_sprite_with_overrides(self) -> None:
        """Sprite shadow overrides are applied."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {
                "shadow_scale": 2.0,
                "shadow_alpha": 0.7,
            }

        result = compute_sprite_shadow(FakeSprite())
        assert result is not None
        ellipse, alpha = result

        # Alpha should be overridden
        assert alpha == 0.7
        # Width should be scaled by 2x
        assert ellipse.width == DEFAULT_SHADOW_WIDTH * 2.0


class TestDeterminism:
    """Tests verifying deterministic behavior across multiple calls."""

    def test_multiple_depths_deterministic_order(self) -> None:
        """Multiple depth values produce consistent relative ordering."""
        depths = [(-10, -100.0), (-5, -50.0), (0, 0.0), (5, 50.0), (10, 100.0)]
        params_list = [
            compute_shadow_params(rl, dz) for rl, dz in depths
        ]

        # Scale should be strictly increasing
        scales = [p.scale for p in params_list]
        for i in range(len(scales) - 1):
            assert scales[i] < scales[i + 1], f"Scale not increasing at index {i}"

        # Alpha should be strictly increasing
        alphas = [p.alpha for p in params_list]
        for i in range(len(alphas) - 1):
            assert alphas[i] < alphas[i + 1], f"Alpha not increasing at index {i}"

    def test_repeated_calls_identical(self) -> None:
        """Repeated calls with same inputs produce identical results."""
        for _ in range(10):
            params = compute_shadow_params(7, 42.5, base_scale=1.2, base_alpha=0.4)
            assert params.scale == pytest.approx(1.419, rel=1e-3)
            assert params.alpha == pytest.approx(0.4365, rel=1e-3)


# =============================================================================
# Contact Shadow Tests
# =============================================================================


class TestContactShadowParamsDataclass:
    """Tests for ContactShadowParams dataclass."""

    def test_contactshadowparams_to_dict(self) -> None:
        params = ContactShadowParams(scale=0.5, alpha=0.5, offset_y=-2.0)
        d = params.to_dict()
        assert d == {"scale": 0.5, "alpha": 0.5, "offset_y": -2.0}

    def test_contactshadowparams_frozen(self) -> None:
        params = ContactShadowParams(scale=0.5, alpha=0.5, offset_y=-2.0)
        with pytest.raises(AttributeError):
            as_any(params).scale = 1.0


class TestComputeContactShadowParams:
    """Tests for compute_contact_shadow_params function."""

    def test_default_contact_is_smaller(self) -> None:
        """Contact shadow should be smaller than base."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        contact = compute_contact_shadow_params(base)
        assert contact.scale < base.scale
        assert contact.scale == pytest.approx(DEFAULT_CONTACT_SCALE, rel=1e-3)

    def test_default_contact_is_darker(self) -> None:
        """Contact shadow should have higher alpha (darker)."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        contact = compute_contact_shadow_params(base)
        assert contact.alpha > base.alpha

    def test_contact_alpha_clamped_to_one(self) -> None:
        """Contact alpha is clamped to 1.0 max."""
        base = ShadowParams(scale=1.0, alpha=0.9, offset_y=-4.0)
        contact = compute_contact_shadow_params(base)
        assert contact.alpha <= 1.0

    def test_contact_offset_closer_to_feet(self) -> None:
        """Contact shadow offset should be closer to sprite (less negative)."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        contact = compute_contact_shadow_params(base)
        assert contact.offset_y > base.offset_y  # Less negative = closer

    def test_custom_contact_scale(self) -> None:
        """Custom contact_scale is applied."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        contact = compute_contact_shadow_params(base, contact_scale=0.3)
        assert contact.scale == pytest.approx(0.3, rel=1e-3)

    def test_custom_contact_alpha_mul(self) -> None:
        """Custom contact_alpha_mul is applied."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        contact = compute_contact_shadow_params(base, contact_alpha_mul=2.0)
        assert contact.alpha == pytest.approx(0.7, rel=1e-3)

    def test_deterministic(self) -> None:
        """Same inputs produce same outputs."""
        base = ShadowParams(scale=1.5, alpha=0.4, offset_y=-6.0)
        c1 = compute_contact_shadow_params(base)
        c2 = compute_contact_shadow_params(base)
        assert c1 == c2


class TestComputeContactShadowEllipse:
    """Tests for compute_contact_shadow_ellipse function."""

    def test_ellipse_smaller_than_base(self) -> None:
        """Contact ellipse should be smaller than base ellipse."""
        base_params = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        contact_params = compute_contact_shadow_params(base_params)

        base_ellipse = compute_shadow_ellipse(100.0, 200.0, base_params)
        contact_ellipse = compute_contact_shadow_ellipse(100.0, 200.0, contact_params)

        assert contact_ellipse.width < base_ellipse.width
        assert contact_ellipse.height < base_ellipse.height

    def test_ellipse_deterministic(self) -> None:
        """Same inputs produce same ellipse."""
        params = ContactShadowParams(scale=0.55, alpha=0.47, offset_y=-2.0)
        e1 = compute_contact_shadow_ellipse(123.456, 789.012, params)
        e2 = compute_contact_shadow_ellipse(123.456, 789.012, params)
        assert e1 == e2


# =============================================================================
# AO Shadow Tests
# =============================================================================


class TestAoShadowParamsDataclass:
    """Tests for AoShadowParams dataclass."""

    def test_aoshadowparams_to_dict(self) -> None:
        params = AoShadowParams(scale=1.5, alpha=0.1, offset_y=-5.0)
        d = params.to_dict()
        assert d == {"scale": 1.5, "alpha": 0.1, "offset_y": -5.0}

    def test_aoshadowparams_frozen(self) -> None:
        params = AoShadowParams(scale=1.5, alpha=0.1, offset_y=-5.0)
        with pytest.raises(AttributeError):
            as_any(params).scale = 2.0


class TestComputeAoShadowParams:
    """Tests for compute_ao_shadow_params function."""

    def test_default_ao_is_larger(self) -> None:
        """AO shadow should be larger than base."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        ao = compute_ao_shadow_params(base)
        assert ao.scale > base.scale
        assert ao.scale == pytest.approx(DEFAULT_AO_SCALE, rel=1e-3)

    def test_default_ao_is_lighter(self) -> None:
        """AO shadow should have lower alpha (lighter/subtler)."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        ao = compute_ao_shadow_params(base)
        assert ao.alpha < base.alpha

    def test_ao_alpha_clamped_max(self) -> None:
        """AO alpha is clamped to 0.5 max (to stay subtle)."""
        base = ShadowParams(scale=1.0, alpha=0.9, offset_y=-4.0)
        ao = compute_ao_shadow_params(base, ao_alpha_mul=1.0)  # Would be 0.9
        assert ao.alpha <= 0.5

    def test_custom_ao_scale(self) -> None:
        """Custom ao_scale is applied."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        ao = compute_ao_shadow_params(base, ao_scale=1.5)
        assert ao.scale == pytest.approx(1.5, rel=1e-3)

    def test_custom_ao_alpha_mul(self) -> None:
        """Custom ao_alpha_mul is applied."""
        base = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        ao = compute_ao_shadow_params(base, ao_alpha_mul=0.5)
        assert ao.alpha == pytest.approx(0.175, rel=1e-3)

    def test_deterministic(self) -> None:
        """Same inputs produce same outputs."""
        base = ShadowParams(scale=1.5, alpha=0.4, offset_y=-6.0)
        a1 = compute_ao_shadow_params(base)
        a2 = compute_ao_shadow_params(base)
        assert a1 == a2


class TestComputeAoShadowEllipse:
    """Tests for compute_ao_shadow_ellipse function."""

    def test_ellipse_larger_than_base(self) -> None:
        """AO ellipse should be larger than base ellipse."""
        base_params = ShadowParams(scale=1.0, alpha=0.35, offset_y=-4.0)
        ao_params = compute_ao_shadow_params(base_params)

        base_ellipse = compute_shadow_ellipse(100.0, 200.0, base_params)
        ao_ellipse = compute_ao_shadow_ellipse(100.0, 200.0, ao_params)

        assert ao_ellipse.width > base_ellipse.width
        assert ao_ellipse.height > base_ellipse.height

    def test_ellipse_deterministic(self) -> None:
        """Same inputs produce same ellipse."""
        params = AoShadowParams(scale=1.25, alpha=0.12, offset_y=-5.0)
        e1 = compute_ao_shadow_ellipse(123.456, 789.012, params)
        e2 = compute_ao_shadow_ellipse(123.456, 789.012, params)
        assert e1 == e2


# =============================================================================
# Shadow Enable/Disable Tests
# =============================================================================


class TestShouldDrawContactShadow:
    """Tests for should_draw_contact_shadow function."""

    def test_none_entity_returns_default_true(self) -> None:
        """None entity_data returns default_enabled."""
        assert should_draw_contact_shadow(None) is True
        assert should_draw_contact_shadow(None, default_enabled=False) is False

    def test_empty_dict_returns_default(self) -> None:
        """Empty dict returns default_enabled."""
        assert should_draw_contact_shadow({}) is True
        assert should_draw_contact_shadow({}, default_enabled=False) is False

    def test_explicit_enabled(self) -> None:
        """Explicit shadow_contact_enabled is respected."""
        assert should_draw_contact_shadow({"shadow_contact_enabled": True}) is True
        assert should_draw_contact_shadow({"shadow_contact_enabled": False}) is False


class TestShouldDrawAoShadow:
    """Tests for should_draw_ao_shadow function."""

    def test_none_entity_returns_default_false(self) -> None:
        """None entity_data returns default_enabled (False by default)."""
        assert should_draw_ao_shadow(None) is False
        assert should_draw_ao_shadow(None, default_enabled=True) is True

    def test_empty_dict_returns_default(self) -> None:
        """Empty dict returns default_enabled."""
        assert should_draw_ao_shadow({}) is False
        assert should_draw_ao_shadow({}, default_enabled=True) is True

    def test_explicit_enabled(self) -> None:
        """Explicit shadow_ao_enabled is respected."""
        assert should_draw_ao_shadow({"shadow_ao_enabled": True}) is True
        assert should_draw_ao_shadow({"shadow_ao_enabled": False}) is False


# =============================================================================
# Extended Override Tests
# =============================================================================


class TestGetShadowOverridesExtended:
    """Tests for extended shadow override extraction."""

    def test_extracts_contact_scale(self) -> None:
        """shadow_contact_scale extracted."""
        overrides = get_shadow_overrides({"shadow_contact_scale": 0.4})
        assert overrides == {"contact_scale": 0.4}

    def test_extracts_contact_alpha(self) -> None:
        """shadow_contact_alpha extracted and clamped to 0..1."""
        assert get_shadow_overrides({"shadow_contact_alpha": 0.6}) == {"contact_alpha": 0.6}
        assert get_shadow_overrides({"shadow_contact_alpha": -0.5}) == {"contact_alpha": 0.0}
        assert get_shadow_overrides({"shadow_contact_alpha": 1.5}) == {"contact_alpha": 1.0}

    def test_multiple_extended_overrides(self) -> None:
        """Multiple contact/AO overrides extracted together."""
        entity = {
            "shadow_scale": 1.5,
            "shadow_contact_scale": 0.4,
            "shadow_contact_alpha": 0.7,
        }
        overrides = get_shadow_overrides(entity)
        assert overrides == {
            "scale_mult": 1.5,
            "contact_scale": 0.4,
            "contact_alpha": 0.7,
        }

    def test_invalid_contact_values_ignored(self) -> None:
        """Invalid contact override values are ignored."""
        entity = {
            "shadow_contact_scale": "not a number",
            "shadow_contact_alpha": None,
        }
        assert get_shadow_overrides(entity) == {}


# =============================================================================
# Multi-Layer Shadow Tests
# =============================================================================


class TestComputeSpriteMultiShadow:
    """Tests for compute_sprite_multi_shadow function."""

    def test_sprite_without_entity_data(self) -> None:
        """Sprite without mesh_entity_data gets default multi-layer shadow."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0

        result = compute_sprite_multi_shadow(FakeSprite())
        assert result is not None
        assert isinstance(result, MultiLayerShadow)
        assert result.base_ellipse is not None
        assert result.contact_ellipse is not None  # Default enabled
        assert result.ao_ellipse is None  # Default disabled

    def test_contact_disabled(self) -> None:
        """Contact shadow disabled via parameter."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0

        result = compute_sprite_multi_shadow(FakeSprite(), contact_enabled=False)
        assert result is not None
        assert result.contact_ellipse is None

    def test_ao_enabled(self) -> None:
        """AO shadow enabled via parameter."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0

        result = compute_sprite_multi_shadow(FakeSprite(), ao_enabled=True)
        assert result is not None
        assert result.ao_ellipse is not None

    def test_base_shadow_disabled_returns_none(self) -> None:
        """If base shadow disabled, entire result is None."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"shadow_enabled": False}

        result = compute_sprite_multi_shadow(FakeSprite())
        assert result is None

    def test_entity_overrides_contact_disabled(self) -> None:
        """Entity can disable contact shadow."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"shadow_contact_enabled": False}

        result = compute_sprite_multi_shadow(FakeSprite(), contact_enabled=True)
        assert result is not None
        assert result.contact_ellipse is None

    def test_entity_overrides_ao_enabled(self) -> None:
        """Entity can enable AO shadow."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"shadow_ao_enabled": True}

        result = compute_sprite_multi_shadow(FakeSprite(), ao_enabled=False)
        assert result is not None
        assert result.ao_ellipse is not None

    def test_layer_ordering_sizes(self) -> None:
        """AO > base > contact size ordering."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0

        result = compute_sprite_multi_shadow(FakeSprite(), ao_enabled=True)
        assert result is not None
        assert result.ao_ellipse is not None
        assert result.contact_ellipse is not None

        # AO should be largest
        assert result.ao_ellipse.width > result.base_ellipse.width
        # Contact should be smallest
        assert result.contact_ellipse.width < result.base_ellipse.width

    def test_deterministic(self) -> None:
        """Same inputs produce same multi-layer shadow."""

        class FakeSprite:
            center_x = 123.456
            center_y = 789.012
            mesh_entity_data = {"render_layer": 5, "depth_z": 25.0}

        r1 = compute_sprite_multi_shadow(FakeSprite(), ao_enabled=True)
        r2 = compute_sprite_multi_shadow(FakeSprite(), ao_enabled=True)
        assert r1 == r2

    def test_contact_alpha_override(self) -> None:
        """Entity contact_alpha override is applied."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"shadow_contact_alpha": 0.9}

        result = compute_sprite_multi_shadow(FakeSprite())
        assert result is not None
        assert result.contact_alpha == pytest.approx(0.9, rel=1e-3)

    def test_contact_scale_override(self) -> None:
        """Entity contact_scale override is applied."""

        class FakeSprite:
            center_x = 100.0
            center_y = 200.0
            mesh_entity_data = {"shadow_contact_scale": 0.3}

        result = compute_sprite_multi_shadow(FakeSprite())
        assert result is not None
        # Contact should use smaller scale
        expected_width = DEFAULT_SHADOW_WIDTH * 0.3
        assert result.contact_ellipse is not None
        assert result.contact_ellipse.width == pytest.approx(expected_width, rel=1e-2)
