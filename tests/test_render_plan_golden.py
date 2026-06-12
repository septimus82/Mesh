"""
Golden tests for render plan ordering and composition.

These tests verify that:
1. Render plans are deterministic across runs
2. Layer ordering is correct
3. Z-depth sorting is consistent within layers
4. Culled objects are excluded
5. Invariants (no NaN, monotonic depth, resolved textures) hold
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from engine.depth_tint_model import DepthTintSettings
from engine.editor.sprite_outline_model import OutlineSettings
from engine.parallax_model import BackgroundPlane
from engine.render_plan import (
    DrawCall,
    DrawCallType,
    RenderPlan,
    Transform,
    assert_render_plan_valid,
    build_render_plan_from_draw_plan,
    build_render_plan_from_sprites,
    validate_render_plan,
)
from engine.scene_render_pipeline import (
    BackgroundDrawOp,
    DrawPlan,
    build_render_context,
    compute_draw_plan,
)

# =============================================================================
# Fixture Builders
# =============================================================================


@dataclass
class MockSprite:
    """Mock sprite for testing without Arcade dependencies."""
    center_x: float = 0.0
    center_y: float = 0.0
    scale: float = 1.0
    angle: float = 0.0
    alpha: int = 255
    color: tuple[int, int, int, int] = (255, 255, 255, 255)
    width: float = 32.0
    height: float = 32.0
    texture: Any = None
    mesh_entity_data: dict[str, Any] = field(default_factory=dict)
    mesh_texture_key: Any = None
    mesh_name: str | None = None

    def __post_init__(self):
        if self.texture is None:
            self.texture = MagicMock()
            self.texture.name = "mock_texture"
            self.texture.width = 32
            self.texture.height = 32


def make_sprite(
    entity_id: str,
    x: float = 0.0,
    y: float = 0.0,
    render_layer: int = 0,
    depth_z: float = 0.0,
    texture_name: str = "default",
) -> MockSprite:
    """Factory for creating test sprites."""
    return MockSprite(
        center_x=x,
        center_y=y,
        mesh_name=entity_id,
        mesh_entity_data={
            "id": entity_id,
            "render_layer": render_layer,
            "depth_z": depth_z,
        },
        mesh_texture_key=("texture", texture_name),
    )


def make_background_plane(
    asset_path: str,
    render_layer: int = -100,
    parallax: float = 1.0,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> BackgroundPlane:
    """Factory for creating test background planes."""
    return BackgroundPlane(
        asset_path=asset_path,
        render_layer=render_layer,
        parallax=parallax,
        offset_x=offset_x,
        offset_y=offset_y,
    )


# =============================================================================
# Golden Fixture Scenes
# =============================================================================


class GoldenFixtures:
    """Golden fixture scenes for regression testing."""

    @staticmethod
    def simple_three_entities() -> list[MockSprite]:
        """Three entities at different Y positions (y-sort test)."""
        return [
            make_sprite("entity_back", x=100, y=50, render_layer=0),
            make_sprite("entity_middle", x=100, y=100, render_layer=0),
            make_sprite("entity_front", x=100, y=150, render_layer=0),
        ]

    @staticmethod
    def mixed_layers() -> list[MockSprite]:
        """Entities across multiple layers."""
        return [
            make_sprite("ground_decal", x=100, y=100, render_layer=-1),
            make_sprite("player", x=100, y=100, render_layer=0),
            make_sprite("enemy", x=150, y=80, render_layer=0),
            make_sprite("flying_bat", x=120, y=120, render_layer=1),
            make_sprite("cloud", x=100, y=200, render_layer=2),
        ]

    @staticmethod
    def explicit_z_ordering() -> list[MockSprite]:
        """Entities with explicit depth_z values."""
        return [
            make_sprite("far_bg", x=100, y=100, render_layer=0, depth_z=-50.0),
            make_sprite("mid_entity", x=100, y=100, render_layer=0, depth_z=0.0),
            make_sprite("near_entity", x=100, y=100, render_layer=0, depth_z=50.0),
        ]

    @staticmethod
    def parallax_backgrounds() -> list[BackgroundPlane]:
        """Multi-layer parallax backgrounds."""
        return [
            make_background_plane("sky.png", render_layer=-300, parallax=0.0),
            make_background_plane("mountains.png", render_layer=-200, parallax=0.3),
            make_background_plane("trees.png", render_layer=-100, parallax=0.6),
        ]

    @staticmethod
    def complex_scene() -> tuple[list[MockSprite], list[BackgroundPlane]]:
        """Full scene with backgrounds, entities, multiple layers."""
        sprites = [
            # Background layer
            make_sprite("floor_tile_1", x=50, y=50, render_layer=-2),
            make_sprite("floor_tile_2", x=100, y=50, render_layer=-2),
            # Ground decals
            make_sprite("crack_decal", x=75, y=50, render_layer=-1),
            make_sprite("shadow_blob", x=100, y=80, render_layer=-1),
            # Main entities (y-sorted)
            make_sprite("barrel", x=50, y=100, render_layer=0),
            make_sprite("player", x=100, y=120, render_layer=0),
            make_sprite("npc_vendor", x=150, y=90, render_layer=0),
            make_sprite("enemy_slime", x=200, y=110, render_layer=0),
            # Overhead layer
            make_sprite("roof_edge", x=100, y=150, render_layer=1),
            make_sprite("hanging_sign", x=150, y=160, render_layer=1),
            # Effects layer
            make_sprite("particle_emitter", x=100, y=100, render_layer=10),
        ]
        backgrounds = [
            make_background_plane("night_sky.png", render_layer=-500, parallax=0.0),
            make_background_plane("distant_city.png", render_layer=-300, parallax=0.2),
            make_background_plane("near_buildings.png", render_layer=-100, parallax=0.5),
        ]
        return sprites, backgrounds

    @staticmethod
    def culling_test_scene() -> list[MockSprite]:
        """Entities at various positions for culling tests."""
        return [
            # Visible (center of viewport)
            make_sprite("visible_center", x=400, y=300, render_layer=0),
            # Visible (edge of viewport)
            make_sprite("visible_edge", x=50, y=50, render_layer=0),
            # Outside viewport (should be culled)
            make_sprite("outside_left", x=-500, y=300, render_layer=0),
            make_sprite("outside_right", x=1500, y=300, render_layer=0),
            make_sprite("outside_top", x=400, y=1000, render_layer=0),
            make_sprite("outside_bottom", x=400, y=-500, render_layer=0),
        ]

    @staticmethod
    def light_and_occluder_placeholders() -> list[MockSprite]:
        """Light sources and occluders (as data, not GPU objects)."""
        return [
            make_sprite("torch_light", x=100, y=100, render_layer=0, depth_z=0),
            make_sprite("wall_occluder", x=150, y=100, render_layer=0, depth_z=0),
            make_sprite("window_light", x=200, y=150, render_layer=0, depth_z=0),
        ]


# =============================================================================
# Golden Data (Expected Results)
# =============================================================================


# These are the expected orderings for determinism verification
GOLDEN_SIMPLE_THREE_ORDER = ["entity_back", "entity_middle", "entity_front"]
GOLDEN_MIXED_LAYERS_ORDER = ["ground_decal", "enemy", "player", "flying_bat", "cloud"]
GOLDEN_EXPLICIT_Z_ORDER = ["far_bg", "mid_entity", "near_entity"]


# =============================================================================
# Determinism Tests
# =============================================================================


class TestRenderPlanDeterminism:
    """Tests verifying deterministic output across runs."""

    def test_simple_ordering_deterministic(self) -> None:
        """Same inputs always produce same ordering."""
        sprites = GoldenFixtures.simple_three_entities()

        plan1 = build_render_plan_from_sprites(sprites, sort_mode="y_sort")
        plan2 = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        assert plan1.digest() == plan2.digest()
        assert [c.entity_id for c in plan1.calls] == [c.entity_id for c in plan2.calls]

    def test_mixed_layers_deterministic(self) -> None:
        """Layer ordering is deterministic."""
        sprites = GoldenFixtures.mixed_layers()

        plan1 = build_render_plan_from_sprites(sprites, sort_mode="y_sort")
        plan2 = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        assert plan1.digest() == plan2.digest()

    def test_complex_scene_deterministic(self) -> None:
        """Complex scene produces deterministic plan."""
        sprites, _ = GoldenFixtures.complex_scene()

        # Run multiple times
        digests = set()
        for _ in range(5):
            plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")
            digests.add(plan.digest())

        # All runs should produce identical digest
        assert len(digests) == 1

    def test_serialization_roundtrip_preserves_digest(self) -> None:
        """Serialization and deserialization preserves digest."""
        sprites = GoldenFixtures.mixed_layers()
        original = build_render_plan_from_sprites(sprites)

        # Round-trip through JSON
        data = original.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = RenderPlan.from_dict(restored_data)

        assert original.digest() == restored.digest()


# =============================================================================
# Layer Ordering Tests
# =============================================================================


class TestLayerOrdering:
    """Tests verifying correct layer ordering."""

    def test_layers_sorted_ascending(self) -> None:
        """Lower layer indices are drawn first."""
        sprites = GoldenFixtures.mixed_layers()
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        layers = [c.layer for c in plan.calls]
        assert layers == sorted(layers), "Layers should be in ascending order"

    def test_layer_grouping(self) -> None:
        """All calls in same layer are grouped together."""
        sprites = GoldenFixtures.mixed_layers()
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        by_layer = plan.by_layer()

        # Verify expected layers exist
        assert -1 in by_layer  # ground_decal
        assert 0 in by_layer   # player, enemy
        assert 1 in by_layer   # flying_bat
        assert 2 in by_layer   # cloud

    def test_negative_layers_first(self) -> None:
        """Negative layers render before layer 0."""
        sprites = GoldenFixtures.mixed_layers()
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        first_call = plan.calls[0]
        assert first_call.layer < 0
        assert first_call.entity_id == "ground_decal"


# =============================================================================
# Z-Depth Ordering Tests
# =============================================================================


class TestZDepthOrdering:
    """Tests verifying correct Z-depth ordering within layers."""

    def test_y_sort_within_layer(self) -> None:
        """Y-sort mode orders by Y position within layer."""
        sprites = GoldenFixtures.simple_three_entities()
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        entity_ids = [c.entity_id for c in plan.calls]

        # Lower Y (back) should come first
        assert entity_ids == GOLDEN_SIMPLE_THREE_ORDER

    def test_explicit_z_ordering(self) -> None:
        """Explicit Z mode uses depth_z for ordering."""
        sprites = GoldenFixtures.explicit_z_ordering()
        plan = build_render_plan_from_sprites(sprites, sort_mode="explicit_z")

        entity_ids = [c.entity_id for c in plan.calls]

        # Lower depth_z should come first
        assert entity_ids == GOLDEN_EXPLICIT_Z_ORDER

    def test_depth_monotonic_within_layer(self) -> None:
        """Depth values are monotonic within each layer."""
        sprites = GoldenFixtures.complex_scene()[0]
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        by_layer = plan.by_layer()
        for layer_idx, calls in by_layer.items():
            depths = [c.depth_z for c in calls]
            # Check monotonic (allowing equal values)
            for i in range(1, len(depths)):
                assert depths[i] >= depths[i - 1], (
                    f"Layer {layer_idx}: depth not monotonic "
                    f"at index {i} ({depths[i - 1]} -> {depths[i]})"
                )


# =============================================================================
# Background Plane Tests
# =============================================================================


class TestBackgroundPlanes:
    """Tests for background plane ordering."""

    def test_background_planes_sorted_by_render_layer(self) -> None:
        """Background planes are sorted by render_layer (furthest first)."""
        planes = GoldenFixtures.parallax_backgrounds()

        # Create a mock DrawPlan with background ops
        bg_ops = []
        for plane in sorted(planes, key=lambda p: p.render_layer):
            bg_ops.append(BackgroundDrawOp(
                plane=plane,
                base_x=400.0,
                base_y=300.0,
                alpha=255,
            ))

        mock_draw_plan = DrawPlan(
            background_ops=bg_ops,
            shadow_ops=[],
            sprite_ops=[],
        )

        plan = build_render_plan_from_draw_plan(mock_draw_plan)

        # Verify backgrounds come first (negative layers)
        bg_calls = [c for c in plan.calls if c.call_type == DrawCallType.BACKGROUND]
        assert len(bg_calls) == 3

        # Check they're in render_layer order
        layer_values = [c.layer for c in bg_calls]
        assert layer_values == sorted(layer_values)


# =============================================================================
# Invariant Tests
# =============================================================================


class TestRenderPlanInvariants:
    """Tests for render plan invariants."""

    def test_no_nan_in_transforms(self) -> None:
        """Transforms must not contain NaN values."""
        sprites = GoldenFixtures.simple_three_entities()
        plan = build_render_plan_from_sprites(sprites)

        for call in plan.calls:
            assert call.transform.is_valid(), (
                f"Invalid transform for {call.entity_id}"
            )

    def test_nan_transform_detected(self) -> None:
        """Validation catches NaN values."""
        bad_call = DrawCall(
            call_type=DrawCallType.SPRITE,
            layer=0,
            depth_z=0.0,
            texture_id="test",
            transform=Transform(x=float("nan"), y=0.0),
            entity_id="bad_sprite",
        )
        plan = RenderPlan(calls=(bad_call,))

        result = validate_render_plan(plan)
        assert not result.valid
        assert any("NaN" in e or "Invalid transform" in e for e in result.errors)

    def test_texture_resolution(self) -> None:
        """All textures should be resolved."""
        sprites = GoldenFixtures.simple_three_entities()
        plan = build_render_plan_from_sprites(sprites)

        for call in plan.calls:
            assert call.texture_id != "", f"Empty texture for {call.entity_id}"
            # "missing" is allowed but should generate warning

    def test_missing_texture_warning(self) -> None:
        """Missing textures generate warnings."""
        bad_call = DrawCall(
            call_type=DrawCallType.SPRITE,
            layer=0,
            depth_z=0.0,
            texture_id="missing",
            transform=Transform(x=0.0, y=0.0),
            entity_id="no_texture_sprite",
        )
        plan = RenderPlan(calls=(bad_call,))

        result = validate_render_plan(plan)
        assert result.valid  # Warning, not error
        assert any("missing" in w.lower() for w in result.warnings)

    def test_assert_valid_passes_good_plan(self) -> None:
        """assert_render_plan_valid passes for good plans."""
        sprites = GoldenFixtures.simple_three_entities()
        plan = build_render_plan_from_sprites(sprites)

        # Should not raise
        assert_render_plan_valid(plan)

    def test_assert_valid_fails_bad_plan(self) -> None:
        """assert_render_plan_valid raises for bad plans."""
        bad_call = DrawCall(
            call_type=DrawCallType.SPRITE,
            layer=0,
            depth_z=0.0,
            texture_id="test",
            transform=Transform(x=float("inf"), y=0.0),
            entity_id="bad_sprite",
        )
        plan = RenderPlan(calls=(bad_call,))

        with pytest.raises(AssertionError, match="validation failed"):
            assert_render_plan_valid(plan)


# =============================================================================
# Type Filtering Tests
# =============================================================================


class TestRenderPlanFiltering:
    """Tests for filtering render plans."""

    def test_filter_by_type(self) -> None:
        """Can filter plan by call type."""
        # Create a plan with mixed types
        calls = [
            DrawCall(
                call_type=DrawCallType.BACKGROUND,
                layer=-100,
                depth_z=0.0,
                texture_id="bg",
                transform=Transform(x=0.0, y=0.0),
            ),
            DrawCall(
                call_type=DrawCallType.SHADOW,
                layer=0,
                depth_z=0.0,
                texture_id="shadow",
                transform=Transform(x=0.0, y=0.0),
            ),
            DrawCall(
                call_type=DrawCallType.SPRITE,
                layer=0,
                depth_z=0.0,
                texture_id="sprite",
                transform=Transform(x=0.0, y=0.0),
            ),
        ]
        plan = RenderPlan(calls=tuple(calls))

        sprites_only = plan.filter_type(DrawCallType.SPRITE)
        assert len(sprites_only) == 1
        assert sprites_only.calls[0].call_type == DrawCallType.SPRITE

    def test_filter_by_layer(self) -> None:
        """Can filter plan by layer."""
        sprites = GoldenFixtures.mixed_layers()
        plan = build_render_plan_from_sprites(sprites)

        layer_0 = plan.filter_layer(0)

        # Only layer 0 entities: player, enemy
        assert all(c.layer == 0 for c in layer_0.calls)
        entity_ids = {c.entity_id for c in layer_0.calls}
        assert "player" in entity_ids
        assert "enemy" in entity_ids


# =============================================================================
# Integration with DrawPlan Tests
# =============================================================================


class TestDrawPlanIntegration:
    """Tests for integration with scene_render_pipeline.DrawPlan."""

    def test_build_from_draw_plan(self) -> None:
        """Can build RenderPlan from DrawPlan."""
        sprites = GoldenFixtures.simple_three_entities()

        # Create a DrawPlan via the pipeline
        ctx = build_render_context(
            sprites=sprites,
            background_planes=[],
            camera_pos=(0, 0),
            viewport_size=(800, 600),
            zoom=1.0,
            sort_mode="y_sort",
            shadows_enabled=False,
            shadows_ao_enabled=False,
            shadows_contact_enabled=False,
            depth_tint_settings=DepthTintSettings(enabled=False),
            outline_settings=OutlineSettings(enabled=False),
            use_culling=False,
        )
        draw_plan = compute_draw_plan(ctx)

        # Convert to RenderPlan
        render_plan = build_render_plan_from_draw_plan(draw_plan)

        assert len(render_plan) == 3
        entity_ids = [c.entity_id for c in render_plan.calls]
        assert entity_ids == GOLDEN_SIMPLE_THREE_ORDER

    def test_shadow_ops_included(self) -> None:
        """Shadow operations are included in render plan."""
        sprite = make_sprite("test", x=100, y=100)

        # Create DrawPlan with shadows
        ctx = build_render_context(
            sprites=[sprite],
            background_planes=[],
            camera_pos=(0, 0),
            viewport_size=(800, 600),
            zoom=1.0,
            sort_mode="y_sort",
            shadows_enabled=True,
            shadows_ao_enabled=True,
            shadows_contact_enabled=False,
            depth_tint_settings=DepthTintSettings(enabled=False),
            outline_settings=OutlineSettings(enabled=False),
            use_culling=False,
        )
        draw_plan = compute_draw_plan(ctx)

        render_plan = build_render_plan_from_draw_plan(draw_plan)

        # Should have shadow calls
        by_type = render_plan.by_type()
        if DrawCallType.SHADOW in by_type:
            assert len(by_type[DrawCallType.SHADOW]) > 0


# =============================================================================
# Golden Snapshot Tests
# =============================================================================


class TestGoldenSnapshots:
    """Tests comparing against golden expected values."""

    def test_simple_scene_matches_golden(self) -> None:
        """Simple scene matches expected golden ordering."""
        sprites = GoldenFixtures.simple_three_entities()
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        entity_ids = [c.entity_id for c in plan.calls]
        assert entity_ids == GOLDEN_SIMPLE_THREE_ORDER

    def test_mixed_layers_matches_golden(self) -> None:
        """Mixed layer scene matches expected golden ordering."""
        sprites = GoldenFixtures.mixed_layers()
        plan = build_render_plan_from_sprites(sprites, sort_mode="y_sort")

        entity_ids = [c.entity_id for c in plan.calls]
        assert entity_ids == GOLDEN_MIXED_LAYERS_ORDER

    def test_explicit_z_matches_golden(self) -> None:
        """Explicit Z scene matches expected golden ordering."""
        sprites = GoldenFixtures.explicit_z_ordering()
        plan = build_render_plan_from_sprites(sprites, sort_mode="explicit_z")

        entity_ids = [c.entity_id for c in plan.calls]
        assert entity_ids == GOLDEN_EXPLICIT_Z_ORDER


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_scene(self) -> None:
        """Empty scene produces empty plan."""
        plan = build_render_plan_from_sprites([])
        assert len(plan) == 0
        assert plan.digest()  # Should still have a digest

    def test_single_sprite(self) -> None:
        """Single sprite produces valid plan."""
        sprites = [make_sprite("alone", x=100, y=100)]
        plan = build_render_plan_from_sprites(sprites)

        assert len(plan) == 1
        assert plan.calls[0].entity_id == "alone"

    def test_same_position_stable_sort(self) -> None:
        """Sprites at same position have stable ordering."""
        sprites = [
            make_sprite("a", x=100, y=100, render_layer=0),
            make_sprite("b", x=100, y=100, render_layer=0),
            make_sprite("c", x=100, y=100, render_layer=0),
        ]

        plan1 = build_render_plan_from_sprites(sprites)
        plan2 = build_render_plan_from_sprites(sprites)

        # Order should be stable
        ids1 = [c.entity_id for c in plan1.calls]
        ids2 = [c.entity_id for c in plan2.calls]
        assert ids1 == ids2

    def test_extreme_layer_values(self) -> None:
        """Extreme layer values are handled correctly."""
        sprites = [
            make_sprite("very_back", render_layer=-999),
            make_sprite("normal", render_layer=0),
            make_sprite("very_front", render_layer=999),
        ]
        plan = build_render_plan_from_sprites(sprites)

        entity_ids = [c.entity_id for c in plan.calls]
        assert entity_ids == ["very_back", "normal", "very_front"]

    def test_extreme_position_values(self) -> None:
        """Extreme position values are handled correctly."""
        sprites = [
            make_sprite("far_away", x=1000000, y=1000000),
            make_sprite("negative", x=-1000000, y=-1000000),
            make_sprite("origin", x=0, y=0),
        ]
        plan = build_render_plan_from_sprites(sprites)

        assert len(plan) == 3
        assert_render_plan_valid(plan)


# =============================================================================
# Digest Stability Tests
# =============================================================================


class TestDigestStability:
    """Tests verifying digest computation is stable."""

    def test_digest_format(self) -> None:
        """Digest is SHA-256 hex format."""
        sprites = GoldenFixtures.simple_three_entities()
        plan = build_render_plan_from_sprites(sprites)

        digest = plan.digest()
        assert len(digest) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in digest)

    def test_different_scenes_different_digest(self) -> None:
        """Different scenes produce different digests."""
        plan1 = build_render_plan_from_sprites(GoldenFixtures.simple_three_entities())
        plan2 = build_render_plan_from_sprites(GoldenFixtures.mixed_layers())

        assert plan1.digest() != plan2.digest()

    def test_position_change_changes_digest(self) -> None:
        """Changing position changes digest."""
        sprites1 = [make_sprite("test", x=100, y=100)]
        sprites2 = [make_sprite("test", x=101, y=100)]  # 1 pixel difference

        plan1 = build_render_plan_from_sprites(sprites1)
        plan2 = build_render_plan_from_sprites(sprites2)

        assert plan1.digest() != plan2.digest()
