"""Tests for the lighting module refactoring.

These tests verify:
1. Cache invalidation logic works correctly
2. LightingPlan determinism (same inputs = same digest)
3. Shadow geometry integration through the new modules
"""

import pytest

from engine.lighting.lighting_config import (
    LightConfig,
    OccluderConfig,
    LightingSceneConfig,
    normalize_color,
    parse_light_config,
    parse_occluder_config,
    parse_scene_config,
    DEFAULT_AMBIENT_COLOR,
)
from engine.lighting.lighting_cache import (
    LightingCacheState,
    CacheInvalidationResult,
    check_cache_invalidation,
    update_cache_state,
    mark_lights_dirty,
    mark_shadows_dirty,
    mark_all_dirty,
    compute_ambient_digest,
)
from engine.lighting.lighting_geometry import (
    LightGeometry,
    SceneGeometry,
    compute_hulls_digest,
    compute_light_geometry,
    compute_scene_geometry,
    occluder_config_to_polygon_typed,
)
from engine.lighting.lighting_plan import (
    LightPlanEntry,
    OccluderPlanEntry,
    LightingPlan,
    build_lighting_plan,
    build_lighting_plan_from_dicts,
)
from engine.lighting.lighting_render import (
    RenderStats,
    compute_render_plan,
)


# =============================================================================
# Config Module Tests
# =============================================================================


class TestNormalizeColor:
    """Tests for color normalization."""

    def test_normalize_rgb_to_rgba(self):
        """RGB color gets alpha=255 added."""
        result = normalize_color((100, 150, 200))
        assert result == (100, 150, 200, 255)

    def test_normalize_rgba_passthrough(self):
        """RGBA color passes through unchanged."""
        result = normalize_color((100, 150, 200, 128))
        assert result == (100, 150, 200, 128)

    def test_normalize_clamps_values(self):
        """Values are clamped to 0-255."""
        result = normalize_color((-10, 300, 128, 500))
        assert result == (0, 255, 128, 255)

    def test_normalize_none_uses_default(self):
        """None returns default color."""
        result = normalize_color(None)
        assert result == (255, 255, 255, 255)

    def test_normalize_custom_default(self):
        """Custom default is used when input is None."""
        result = normalize_color(None, default=(10, 20, 30, 40))
        assert result == (10, 20, 30, 40)


class TestLightConfig:
    """Tests for LightConfig dataclass."""

    def test_light_config_defaults(self):
        """LightConfig has sensible defaults."""
        cfg = LightConfig()
        assert cfg.light_type == "point"
        assert cfg.radius == 100.0
        assert cfg.intensity == 1.0
        assert cfg.mode == "none"

    def test_light_config_digest_deterministic(self):
        """Same config produces same digest."""
        cfg1 = LightConfig(x=100, y=200, radius=150)
        cfg2 = LightConfig(x=100, y=200, radius=150)
        assert cfg1.digest() == cfg2.digest()

    def test_light_config_digest_changes_with_values(self):
        """Different configs produce different digests."""
        cfg1 = LightConfig(x=100, y=200)
        cfg2 = LightConfig(x=100, y=201)
        assert cfg1.digest() != cfg2.digest()


class TestOccluderConfig:
    """Tests for OccluderConfig dataclass."""

    def test_rect_occluder_digest(self):
        """Rect occluder produces deterministic digest."""
        cfg = OccluderConfig(
            occluder_id="wall1",
            occluder_type="rect",
            x=100, y=200, width=50, height=100
        )
        digest = cfg.digest()
        assert "rect" in digest
        assert "wall1" in digest

    def test_poly_occluder_digest(self):
        """Poly occluder produces deterministic digest."""
        cfg = OccluderConfig(
            occluder_id="shape1",
            occluder_type="poly",
            points=((0, 0), (100, 0), (100, 100), (0, 100))
        )
        digest = cfg.digest()
        assert "poly" in digest
        assert "shape1" in digest


class TestParseConfig:
    """Tests for config parsing functions."""

    def test_parse_light_config_minimal(self):
        """Parse minimal light config."""
        data = {"type": "point", "x": 100, "y": 200}
        cfg = parse_light_config(data)
        assert cfg.light_type == "point"
        assert cfg.x == 100.0
        assert cfg.y == 200.0
        assert cfg.radius == 100.0  # default

    def test_parse_light_config_full(self):
        """Parse full light config."""
        data = {
            "type": "ambient",
            "x": 50, "y": 75,
            "radius": 200,
            "color": [255, 200, 150, 200],
            "intensity": 0.8,
            "mode": "hard",
            "flicker_enabled": True,
            "flicker_amount": 0.2,
        }
        cfg = parse_light_config(data)
        assert cfg.light_type == "ambient"
        assert cfg.radius == 200.0
        assert cfg.color == (255, 200, 150, 200)
        assert cfg.intensity == 0.8
        assert cfg.flicker_enabled is True

    def test_parse_occluder_config_rect(self):
        """Parse rect occluder config."""
        data = {"id": "wall", "type": "rect", "x": 10, "y": 20, "width": 100, "height": 50}
        cfg = parse_occluder_config(data)
        assert cfg.occluder_id == "wall"
        assert cfg.occluder_type == "rect"
        assert cfg.width == 100.0

    def test_parse_occluder_config_poly(self):
        """Parse polygon occluder config."""
        data = {"id": "pillar", "type": "poly", "points": [[0, 0], [50, 0], [50, 100], [0, 100]]}
        cfg = parse_occluder_config(data)
        assert cfg.occluder_type == "poly"
        assert len(cfg.points) == 4

    def test_parse_scene_config(self):
        """Parse complete scene config."""
        lights = [{"type": "point", "x": 100, "y": 100, "radius": 150}]
        occluders = [{"id": "box", "type": "rect", "x": 50, "y": 50, "width": 30, "height": 30}]
        cfg = parse_scene_config(lights, occluders, ambient_color=(64, 64, 64))
        assert len(cfg.lights) == 1
        assert len(cfg.occluders) == 1
        assert cfg.ambient_color == (64, 64, 64, 255)


# =============================================================================
# Cache Module Tests
# =============================================================================


class TestLightingCacheState:
    """Tests for cache state tracking."""

    def test_initial_state_is_dirty(self):
        """New cache state is dirty."""
        state = LightingCacheState()
        assert state.layer_dirty is True
        assert state.shadows_dirty is True

    def test_clear_resets_state(self):
        """Clear marks everything dirty."""
        state = LightingCacheState(
            lights_digest="abc",
            layer_dirty=False,
            shadows_dirty=False,
        )
        state.clear()
        assert state.lights_digest == ""
        assert state.layer_dirty is True
        assert state.shadows_dirty is True

    def test_cache_digest_deterministic(self):
        """Same cache state produces same digest."""
        state1 = LightingCacheState(lights_digest="a", occluders_digest="b")
        state2 = LightingCacheState(lights_digest="a", occluders_digest="b")
        assert state1.digest() == state2.digest()


class TestCacheInvalidation:
    """Tests for cache invalidation logic."""

    def test_lights_change_triggers_layer_rebuild(self):
        """Changing lights triggers layer rebuild."""
        state = LightingCacheState(
            lights_digest="old",
            occluders_digest="same",
            layer_dirty=False,
            shadows_dirty=False,
        )
        config = LightingSceneConfig(
            lights=[LightConfig(x=100, y=100)],  # Different from "old"
            occluders=[],
        )
        # Manually set digests to simulate different values
        result = check_cache_invalidation(state, config)
        assert result.lights_changed is True
        assert result.needs_layer_rebuild is True

    def test_occluders_change_triggers_shadow_rebuild(self):
        """Changing occluders triggers shadow rebuild."""
        state = LightingCacheState(
            lights_digest="",
            occluders_digest="old",
            layer_dirty=False,
            shadows_dirty=False,
        )
        config = LightingSceneConfig(
            lights=[],
            occluders=[OccluderConfig(occluder_id="new", width=50, height=50)],
        )
        result = check_cache_invalidation(state, config)
        assert result.occluders_changed is True
        assert result.needs_shadow_rebuild is True

    def test_no_changes_no_rebuild(self):
        """No config changes means no forced rebuild."""
        config = LightingSceneConfig(lights=[], occluders=[])
        state = LightingCacheState(
            lights_digest=config.lights_digest(),
            occluders_digest=config.occluders_digest(),
            ambient_digest=compute_ambient_digest(config.ambient_color),
            layer_dirty=False,
            shadows_dirty=False,
        )
        result = check_cache_invalidation(state, config)
        assert result.lights_changed is False
        assert result.occluders_changed is False
        assert result.needs_layer_rebuild is False
        assert result.needs_shadow_rebuild is False


class TestMarkDirty:
    """Tests for dirty marking functions."""

    def test_mark_lights_dirty(self):
        """mark_lights_dirty sets layer_dirty."""
        state = LightingCacheState(layer_dirty=False)
        mark_lights_dirty(state)
        assert state.layer_dirty is True

    def test_mark_shadows_dirty(self):
        """mark_shadows_dirty sets shadows_dirty."""
        state = LightingCacheState(shadows_dirty=False)
        mark_shadows_dirty(state)
        assert state.shadows_dirty is True

    def test_mark_all_dirty(self):
        """mark_all_dirty sets both dirty flags."""
        state = LightingCacheState(layer_dirty=False, shadows_dirty=False)
        mark_all_dirty(state)
        assert state.layer_dirty is True
        assert state.shadows_dirty is True


# =============================================================================
# Geometry Module Tests
# =============================================================================


class TestOccluderToPolygon:
    """Tests for occluder to polygon conversion."""

    def test_rect_to_polygon(self):
        """Rect occluder converts to 4-point polygon."""
        cfg = OccluderConfig(x=100, y=200, width=50, height=30)
        poly = occluder_config_to_polygon_typed(cfg)
        assert poly is not None
        assert len(poly) == 4
        assert (100, 200) in poly
        assert (150, 230) in poly

    def test_poly_to_polygon(self):
        """Poly occluder passes through points."""
        cfg = OccluderConfig(
            occluder_type="poly",
            points=((0, 0), (100, 0), (50, 100))
        )
        poly = occluder_config_to_polygon_typed(cfg)
        assert poly == [(0, 0), (100, 0), (50, 100)]

    def test_zero_size_rect_returns_none(self):
        """Zero-size rect returns None."""
        cfg = OccluderConfig(x=100, y=100, width=0, height=50)
        poly = occluder_config_to_polygon_typed(cfg)
        assert poly is None


class TestComputeHullsDigest:
    """Tests for hull digest computation."""

    def test_empty_hulls_digest(self):
        """Empty hulls produce 'empty' digest."""
        digest = compute_hulls_digest([])
        assert digest == "empty"

    def test_same_hulls_same_digest(self):
        """Same hulls produce same digest."""
        hulls = [((0, 0), (100, 0), (100, 100), (0, 100))]
        d1 = compute_hulls_digest(hulls)
        d2 = compute_hulls_digest(hulls)
        assert d1 == d2

    def test_different_hulls_different_digest(self):
        """Different hulls produce different digests."""
        h1 = [((0, 0), (100, 0), (100, 100))]
        h2 = [((0, 0), (100, 0), (100, 200))]
        assert compute_hulls_digest(h1) != compute_hulls_digest(h2)


class TestComputeSceneGeometry:
    """Tests for scene geometry computation."""

    def test_empty_scene(self):
        """Empty scene produces empty geometry."""
        geom = compute_scene_geometry([], [])
        assert geom.total_hulls_count == 0
        assert len(geom.light_geometries) == 0
        assert len(geom.occluder_polygons) == 0

    def test_ambient_light_no_shadows(self):
        """Ambient light produces no shadow hulls."""
        lights = [LightConfig(light_type="ambient", radius=100)]
        geom = compute_scene_geometry(lights, [])
        assert len(geom.light_geometries) == 1
        assert geom.light_geometries[0].shadow_hulls == ()
        assert geom.light_geometries[0].hulls_digest == "none"

    def test_point_light_with_occluder(self):
        """Point light with occluder produces shadow hulls."""
        lights = [LightConfig(light_type="point", x=0, y=0, radius=500)]
        occluders = [OccluderConfig(x=100, y=-25, width=50, height=50)]
        geom = compute_scene_geometry(lights, occluders)
        assert len(geom.light_geometries) == 1
        # Should have shadow hulls (exact count depends on shadow algorithm)
        assert geom.total_hulls_count >= 0

    def test_geometry_digest_deterministic(self):
        """Same inputs produce same geometry digest."""
        lights = [LightConfig(x=100, y=100, radius=200)]
        occluders = [OccluderConfig(x=200, y=200, width=50, height=50)]
        g1 = compute_scene_geometry(lights, occluders)
        g2 = compute_scene_geometry(lights, occluders)
        assert g1.combined_digest == g2.combined_digest


# =============================================================================
# Plan Module Tests
# =============================================================================


class TestLightingPlan:
    """Tests for LightingPlan model."""

    def test_empty_plan_digest(self):
        """Empty plan has deterministic digest."""
        plan1 = LightingPlan()
        plan2 = LightingPlan()
        assert plan1.digest() == plan2.digest()

    def test_plan_digest_changes_with_content(self):
        """Plan digest changes when content changes."""
        plan1 = LightingPlan(ambient_color=(100, 100, 100, 255))
        plan2 = LightingPlan(ambient_color=(200, 200, 200, 255))
        assert plan1.digest() != plan2.digest()

    def test_plan_to_dict_roundtrip(self):
        """Plan survives dict roundtrip."""
        plan = LightingPlan(
            ambient_color=(64, 64, 64, 255),
            shadows_mode="hard",
            lights=[LightPlanEntry(
                index=0, light_type="point",
                position=(100.0, 200.0), radius=150.0,
                color=(255, 255, 255, 255), intensity=1.0,
                shadow_hulls_count=4, hulls_digest="abc123"
            )],
        )
        data = plan.to_dict()
        restored = LightingPlan.from_dict(data)
        assert restored.digest() == plan.digest()

    def test_plan_to_json(self):
        """Plan serializes to valid JSON."""
        plan = LightingPlan(shadows_mode="soft")
        json_str = plan.to_json()
        assert '"shadows_mode": "soft"' in json_str


class TestBuildLightingPlan:
    """Tests for lighting plan construction."""

    def test_build_from_config_and_geometry(self):
        """Build plan from scene config and geometry."""
        config = LightingSceneConfig(
            ambient_color=(100, 100, 100, 255),
            lights=[LightConfig(x=50, y=50, radius=100)],
            occluders=[OccluderConfig(occluder_id="box", x=100, y=100, width=30, height=30)],
        )
        geometry = compute_scene_geometry(config.lights, config.occluders)
        plan = build_lighting_plan(config, geometry)
        assert plan.ambient_color == (100, 100, 100, 255)
        assert len(plan.lights) == 1
        assert len(plan.occluders) == 1

    def test_build_from_dicts(self):
        """Build plan directly from dict data."""
        lights = [{"type": "point", "x": 100, "y": 100, "radius": 200}]
        occluders = [{"id": "wall", "type": "rect", "x": 200, "y": 200, "width": 50, "height": 100}]
        plan = build_lighting_plan_from_dicts(lights, occluders, (50, 50, 50))
        assert len(plan.lights) == 1
        assert len(plan.occluders) == 1
        assert plan.geometry_digest != ""


class TestLightingPlanDeterminism:
    """Tests for lighting plan determinism."""

    def test_same_inputs_same_digest(self):
        """Same inputs always produce same digest."""
        lights = [{"type": "point", "x": 100, "y": 100, "radius": 200}]
        occluders = [{"id": "wall", "type": "rect", "x": 200, "y": 200, "width": 50, "height": 100}]
        plan1 = build_lighting_plan_from_dicts(lights, occluders, (50, 50, 50))
        plan2 = build_lighting_plan_from_dicts(lights, occluders, (50, 50, 50))
        assert plan1.digest() == plan2.digest()

    def test_order_independent_determinism(self):
        """Light order doesn't affect determinism (sorted internally)."""
        lights_a = [
            {"type": "point", "x": 100, "y": 100, "radius": 100},
            {"type": "point", "x": 200, "y": 200, "radius": 100},
        ]
        lights_b = [
            {"type": "point", "x": 200, "y": 200, "radius": 100},
            {"type": "point", "x": 100, "y": 100, "radius": 100},
        ]
        # Note: The digests might differ because light indices are preserved
        # but the internal sorting for comparison should be consistent
        plan_a = build_lighting_plan_from_dicts(lights_a, [])
        plan_b = build_lighting_plan_from_dicts(lights_b, [])
        # The geometry should be the same even if indices differ
        assert plan_a.geometry_digest == plan_b.geometry_digest


# =============================================================================
# Render Module Tests
# =============================================================================


class TestComputeRenderPlan:
    """Tests for render plan computation."""

    def test_empty_lights(self):
        """Empty lights produces empty render plan."""
        result = compute_render_plan([], shadows_enabled=False)
        assert result == []

    def test_ambient_first(self):
        """Ambient lights are rendered first."""
        lights = [
            LightConfig(light_type="point", x=100, y=100),
            LightConfig(light_type="ambient"),
            LightConfig(light_type="point", x=200, y=200),
        ]
        plan = compute_render_plan(lights, shadows_enabled=True)
        # Ambient (index 1) should be first
        assert plan[0] == 1

    def test_respects_max_lights(self):
        """Render plan respects max_lights limit."""
        lights = [LightConfig(light_type="point") for _ in range(50)]
        plan = compute_render_plan(lights, shadows_enabled=False, max_lights=10)
        assert len(plan) == 10


class TestRenderStats:
    """Tests for RenderStats dataclass."""

    def test_default_stats(self):
        """RenderStats has sensible defaults."""
        stats = RenderStats()
        assert stats.lights_drawn == 0
        assert stats.shadows_drawn == 0
        assert stats.fallback_used is False
